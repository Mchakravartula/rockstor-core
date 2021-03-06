"""
Copyright (c) 2012-2013 RockStor, Inc. <http://rockstor.com>
This file is part of RockStor.

RockStor is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published
by the Free Software Foundation; either version 2 of the License,
or (at your option) any later version.

RockStor is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.
"""
import re
from contextlib import contextmanager
from storageadmin.exceptions import RockStorAPIException
from rest_framework.response import Response
from django.db import transaction
from storageadmin.models import (Disk, Pool, Share)
from fs.btrfs import (scan_disks, wipe_disk, blink_disk, enable_quota,
                      btrfs_uuid, pool_usage, mount_root, get_pool_info,
                      pool_raid, enable_quota)
from storageadmin.serializers import DiskInfoSerializer
from storageadmin.util import handle_exception
from share_helpers import (import_shares, import_snapshots)
from django.conf import settings
import rest_framework_custom as rfc
from system import smart
from copy import deepcopy
import uuid
import logging

logger = logging.getLogger(__name__)


class DiskMixin(object):
    serializer_class = DiskInfoSerializer

    @staticmethod
    @transaction.atomic
    def _update_disk_state():
        """
        A db atomic method to update the database of attached disks / drives.
        Works only on device serial numbers for drive identification.
        Calls scan_disks to establish the current connected drives info.
        Initially removes duplicate by serial number db entries to deal
        with legacy db states and obfuscates all previous device names as they
        are transient. The drive database is then updated with the attached
        disks info and previously known drives no longer found attached are
        marked as offline. All offline drives have their SMART availability and
        activation status removed and all attached drives have their SMART
        availability assessed and activated if available.
        :return: serialized models of attached and missing disks via serial num
        """
        # Acquire a list (namedtupil collection) of attached drives > min size
        disks = scan_disks(settings.MIN_DISK_SIZE)
        serial_numbers_seen = []
        # Make sane our db entries in view of what we know we have attached.
        # Device serial number is only known external unique entry, scan_disks
        # make this so in the case of empty or repeat entries by providing
        # fake serial numbers which are in turn flagged via WebUI as unreliable.
        # 1) scrub all device names with unique but nonsense uuid4
        # 1) mark all offline disks as such via db flag
        # 2) mark all offline disks smart available and enabled flags as False
        logger.info('update_disk_state() Called')
        for do in Disk.objects.all():
            # Replace all device names with a unique placeholder on each scan
            # N.B. do not optimize by re-using uuid index as this could lead
            # to a non refreshed webui acting upon an entry that is different
            # from that shown to the user.
            do.name = str(uuid.uuid4()).replace('-', '')  # 32 chars long
            # Delete duplicate or fake by serial number db disk entries.
            # It makes no sense to save fake serial number drives between scans
            # as on each scan the serial number is re-generated anyway.
            if (do.serial in serial_numbers_seen) or (len(do.serial) == 48):
                logger.info('Deleting duplicate or fake (by serial) Disk db '
                            'entry. Serial = %s' % do.serial)
                do.delete()  # django >=1.9 returns a dict of deleted items.
                # Continue onto next db disk object as nothing more to process.
                continue
            # first encounter of this serial in the db so stash it for reference
            serial_numbers_seen.append(deepcopy(do.serial))
            # Look for devices (by serial number) that are in the db but not in
            # our disk scan, ie offline / missing.
            if (do.serial not in [d.serial for d in disks]):
                # update the db entry as offline
                do.offline = True
                # disable S.M.A.R.T available and enabled flags.
                do.smart_available = do.smart_enabled = False
            do.save()  # make sure all updates are flushed to db
        # Our db now has no device name info as all dev names are place holders.
        # Iterate over attached drives to update the db's knowledge of them.
        # Kernel dev names are unique so safe to overwrite our db unique name.
        for d in disks:
            # start with an empty disk object
            dob = None
            # If the db has an entry with this disk's serial number then
            # use this db entry and update the device name from our recent scan.
            if (Disk.objects.filter(serial=d.serial).exists()):
                dob = Disk.objects.get(serial=d.serial)
                dob.name = d.name
            else:
                # We have an assumed new disk entry as no serial match in db.
                # Build a new entry for this disk.
                dob = Disk(name=d.name, serial=d.serial)
            # Update the db disk object (existing or new) with our scanned info
            dob.size = d.size
            dob.parted = d.parted
            dob.offline = False  # as we are iterating over attached devices
            dob.model = d.model
            dob.transport = d.transport
            dob.vendor = d.vendor
            dob.btrfs_uuid = d.btrfs_uuid
            # If attached disk has an fs and it isn't btrfs
            if (d.fstype is not None and d.fstype != 'btrfs'):
                dob.btrfs_uuid = None
                dob.parted = True
            # If our existing Pool db knows of this disk's pool via it's label:
            if (Pool.objects.filter(name=d.label).exists()):
                # update the disk db object's pool field accordingly.
                dob.pool = Pool.objects.get(name=d.label)

                #this is for backwards compatibility. root pools created
                #before the pool.role migration need this. It can safely be
                #removed a few versions after 3.8-11 or when we reset migrations.
                if (d.root is True):
                    dob.pool.role = 'root'
                    dob.pool.save()
            else:  # this disk is not known to exist in any pool via it's label
                dob.pool = None
            # If no pool has yet been found with this disk's label in and
            # the attached disk is our root disk (flagged by scan_disks)
            if (dob.pool is None and d.root is True):
                # setup our special root disk db entry in Pool
                #@todo: dynamically retrieve raid level.
                p = Pool(name=d.label, raid='single', role='root')
                p.disk_set.add(dob)
                p.save()
                # update disk db object to reflect special root pool status
                dob.pool = p
                dob.save()
                p.size = pool_usage(mount_root(p))[0]
                enable_quota(p)
                p.uuid = btrfs_uuid(dob.name)
                p.save()
            # save our updated db disk object
            dob.save()
        # Update online db entries with S.M.A.R.T availability and status.
        for do in Disk.objects.all():
            # find all the not offline db entries
            if (not do.offline):
                # We have an attached disk db entry
                if re.match('vd', do.name):
                    # Virtio disks (named vd*) have no smart capability.
                    # avoids cluttering logs with exceptions on these devices.
                    do.smart_available = do.smart_enabled = False
                    continue
                # try to establish smart availability and status and update db
                try:
                    # for non ata/sata drives
                    do.smart_available, do.smart_enabled = smart.available(do.name)
                except Exception, e:
                    logger.exception(e)
                    do.smart_available = do.smart_enabled = False
            do.save()
        ds = DiskInfoSerializer(Disk.objects.all().order_by('name'), many=True)
        return Response(ds.data)


class DiskListView(DiskMixin, rfc.GenericView):
    serializer_class = DiskInfoSerializer

    def get_queryset(self, *args, **kwargs):
        with self._handle_exception(self.request):
            return Disk.objects.all().order_by('name')

    def post(self, request, command, dname=None):
        with self._handle_exception(request):
            if (command == 'scan'):
                return self._update_disk_state()

        e_msg = ('Unsupported command(%s).' % command)
        handle_exception(Exception(e_msg), request)


class DiskDetailView(rfc.GenericView):
    serializer_class = DiskInfoSerializer

    @staticmethod
    def _validate_disk(dname, request):
        try:
            return Disk.objects.get(name=dname)
        except:
            e_msg = ('Disk(%s) does not exist' % dname)
            handle_exception(Exception(e_msg), request)

    def get(self, *args, **kwargs):
        if 'dname' in self.kwargs:
            try:
                data = Disk.objects.get(name=self.kwargs['dname'])
                serialized_data = DiskInfoSerializer(data)
                return Response(serialized_data.data)
            except:
                return Response()

    @transaction.atomic
    def delete(self, request, dname):
        try:
            disk = Disk.objects.get(name=dname)
        except:
            e_msg = ('Disk: %s does not exist' % dname)
            handle_exception(Exception(e_msg), request)

        if (disk.offline is not True):
            e_msg = ('Disk: %s is not offline. Cannot delete' % dname)
            handle_exception(Exception(e_msg), request)

        try:
            disk.delete()
            return Response()
        except Exception, e:
            e_msg = ('Could not remove disk(%s) due to system error' % dname)
            logger.exception(e)
            handle_exception(Exception(e_msg), request)

    def post(self, request, command, dname):
        with self._handle_exception(request):
            if (command == 'wipe'):
                return self._wipe(dname, request)
            if (command == 'btrfs-wipe'):
                return self._wipe(dname, request)
            if (command == 'btrfs-disk-import'):
                return self._btrfs_disk_import(dname, request)
            if (command == 'blink-drive'):
                return self._blink_drive(dname, request)
            if (command == 'enable-smart'):
                return self._toggle_smart(dname, request, enable=True)
            if (command == 'disable-smart'):
                return self._toggle_smart(dname, request)

        e_msg = ('Unsupported command(%s). Valid commands are wipe, btrfs-wipe,'
                 ' btrfs-disk-import, blink-drive, enable-smart, disable-smart' % command)
        handle_exception(Exception(e_msg), request)

    @transaction.atomic
    def _wipe(self, dname, request):
        disk = self._validate_disk(dname, request)
        wipe_disk(disk.name)
        disk.parted = False
        disk.btrfs_uuid = None
        disk.save()
        return Response(DiskInfoSerializer(disk).data)

    @transaction.atomic
    def _btrfs_disk_import(self, dname, request):
        try:
            disk = self._validate_disk(dname, request)
            p_info = get_pool_info(dname)
            # get some options from saved config?
            po = Pool(name=p_info['label'], raid="unknown")
            # need to save it so disk objects get updated properly in the for
            # loop below.
            po.save()
            for d in p_info['disks']:
                do = Disk.objects.get(name=d)
                do.pool = po
                do.parted = False
                do.save()
                mount_root(po)
            po.raid = pool_raid('%s%s' % (settings.MNT_PT, po.name))['data']
            po.size = pool_usage('%s%s' % (settings.MNT_PT, po.name))[0]
            po.save()
            enable_quota(po)
            import_shares(po, request)
            for share in Share.objects.filter(pool=po):
                import_snapshots(share)
            return Response(DiskInfoSerializer(disk).data)
        except Exception, e:
            e_msg = ('Failed to import any pool on this device(%s). Error: %s'
                     % (dname, e.__str__()))
            handle_exception(Exception(e_msg), request)

    @classmethod
    @transaction.atomic
    def _toggle_smart(cls, dname, request, enable=False):
        disk = cls._validate_disk(dname, request)
        if (not disk.smart_available):
            e_msg = ('S.M.A.R.T support is not available on this Disk(%s)' % dname)
            handle_exception(Exception(e_msg), request)
        smart.toggle_smart(disk.name, enable)
        disk.smart_enabled = enable
        disk.save()
        return Response(DiskInfoSerializer(disk).data)

    @classmethod
    def _blink_drive(cls, dname, request):
        disk = cls._validate_disk(dname, request)
        total_time = int(request.data.get('total_time', 90))
        blink_time = int(request.data.get('blink_time', 15))
        sleep_time = int(request.data.get('sleep_time', 5))
        blink_disk(disk.name, total_time, blink_time, sleep_time)
        return Response()
