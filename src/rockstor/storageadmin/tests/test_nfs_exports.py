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


from rest_framework import status
from rest_framework.test import APITestCase
from system.services import systemctl
import mock
from mock import patch
from storageadmin.tests.test_api import APITestMixin

class NFSExportTests(APITestMixin, APITestCase):
    fixtures = ['fix3.json']
    BASE_URL = '/api/nfs-exports'

    @classmethod
    def setUpClass(cls):
        super(NFSExportTests, cls).setUpClass()

        # post mocks
        cls.patch_mount_share = patch('storageadmin.views.nfs_exports.mount_share')
        cls.mock_mount_share = cls.patch_mount_share.start()
        cls.mock_mount_share.return_value = 'foo'

        cls.patch_is_share_mounted = patch('storageadmin.views.nfs_exports.is_share_mounted')
        cls.mock_is_share_mounted = cls.patch_is_share_mounted.start()
        cls.mock_is_share_mounted.return_value = True


    @classmethod
    def tearDownClass(cls):
        super(NFSExportTests, cls).tearDownClass()

    def test_get(self):
        """
        Test GET request
        1. Get base URL
        2. Get request with id
        """
        # get base URL
        self.get_base(self.BASE_URL)
        
        # get nfsexport with id =3
        response = self.client.get('%s/3' % self.BASE_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response)

        # get nfsexport with id =5
        response = self.client.get('%s/5' % self.BASE_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response)
        
    def test_post_requests(self):
    
        # nfs-export without selecting the shares   
        data = {'host_str': '*.test.co.uk',  'mod_choice': 'rw', 'sync_choice': 'async'}
        response = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response.status_code,
                         status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response.data)
        e_msg = ('Cannot export without specifying shares')
        self.assertEqual(response.data['detail'], e_msg)
        
        # nfs-export without selecting the share already mounted   
        data = {'shares': ('share4', ), 'host_str': '*.test.co.uk', 'mod_choice': 'rw', 'sync_choice': 'async'}
        self.mock_is_share_mounted.return_value = False
        response = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response.status_code,
                         status.HTTP_200_OK, msg=response.data)
        self.mock_is_share_mounted.return_value = True
        
        # happy path
        data = {'shares': ('share1', ), 'host_str': '*.test.co.uk',  'mod_choice': 'rw', 'sync_choice': 'async'}
        response = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response.status_code,
                         status.HTTP_200_OK, msg=response.data)
                         
    def test_post_invalid_host_string1(self):
        
        # nfs-export with invalid host_str  
        data = {'shares': ('share5', ),'host_str': '%%%%',  'mod_choice': 'rw', 'sync_choice': 'async'}
        response = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response.status_code,
                         status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response.data)
        e_msg = ('Host String: %%%% is not valid')
        self.assertEqual(response.data['detail'], e_msg)
     
    def test_post_invalid_host_string2(self):
        
        # nfs-export with empty host_str  
        data = {'shares': ('share5', ),'host_str': '',  'mod_choice': 'rw', 'sync_choice': 'async'}
        response = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response.status_code,
                         status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response.data)
        e_msg = ('Cannot export without host string')
        self.assertEqual(response.data['detail'], e_msg)
            
    def test_post_invalid_admin_host1(self):  
      
        # nfs-export with invalid admin_host 
        data = {'shares': ('share6', ), 'host_str': '*.test.co.uk', 'admin_host':'###', 'mod_choice': 'rw', 'sync_choice': 'async'}
        response = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response.status_code,
                         status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response.data)
        e_msg = ('Admin host: ### is not valid')
        self.assertEqual(response.data['detail'], e_msg)
    
    def test_post_invalid_admin_host2(self):  
      
        # nfs-export with invalid admin_host 
        data = {'shares': ('share6', ), 'host_str': '*.test.co.uk', 'admin_host':'1234', 'mod_choice': 'rw', 'sync_choice': 'async'}
        response = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response.status_code,
                         status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response.data)
        e_msg = ('Admin host: 1234 is not valid')
        self.assertEqual(response.data['detail'], e_msg)
        
    def test_post_invalid_admin_host3(self):  
      
        # nfs-export with invalid admin_host 
        data = {'shares': ('share6', ), 'host_str': '*.test.co.uk', 'admin_host':'rocky', 'mod_choice': 'rw', 'sync_choice': 'async'}
        response = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response.status_code,
                         status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response.data)
        e_msg = ('Admin host: rocky is not valid')
        self.assertEqual(response.data['detail'], e_msg)    
 
    def test_put_requests(self):
        """
        1. Edit samba that does not exists
        2. Edit samba
        """
        
        # nfs-export without selecting the shares 
        nfs_id = 1  
        data = {'host_str': '*.test.co.uk', 'mod_choice': 'rw', 'sync_choice': 'async'}
        response = self.client.put('%s/%d' % (self.BASE_URL, nfs_id), data=data)
        self.assertEqual(response.status_code,
                         status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response.data)
        e_msg = ('Cannot export without specifying shares')
        self.assertEqual(response.data['detail'], e_msg)
        
        nfs_id = 1
        data = {'shares': ('share1','share4' ), 'host_str': '*.test.co.uk', 'mod_choice': 'rw', 'sync_choice': 'async'}
        self.mock_is_share_mounted.return_value = False
        response = self.client.put('%s/%d' % (self.BASE_URL, nfs_id), data=data)
        self.assertEqual(response.status_code,
                         status.HTTP_200_OK, msg=response.data)
        self.mock_is_share_mounted.return_value = True
        
        # edit nfs export
        nfs_id = 1
        data = {'shares': ('share1','share4' ), 'host_str': '*.test.co.uk', 'mod_choice': 'rw', 'sync_choice': 'async'}
        response = self.client.put('%s/%d' % (self.BASE_URL, nfs_id), data=data)
        self.assertEqual(response.status_code,
                         status.HTTP_200_OK, msg=response.data)
                         
        # edit nfs export, replace the existing share with new one 
        nfs_id = 1
        data = {'shares': ('share3', ), 'host_str': '*.test.co.uk',  'mod_choice': 'rw', 'sync_choice': 'async'}
        response = self.client.put('%s/%d' % (self.BASE_URL, nfs_id), data=data)
        self.assertEqual(response.status_code,
                         status.HTTP_200_OK, msg=response.data)

    def test_put_invalid_host_string1(self):
        
        # edit nfs-export with invalid host_str
        nfs_id = 1  
        data = {'shares': ('share5', ),'host_str': '%%%%',  'mod_choice': 'rw', 'sync_choice': 'async'}
        response = self.client.put('%s/%d' % (self.BASE_URL, nfs_id), data=data)
        self.assertEqual(response.status_code,
                         status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response.data)
        e_msg = ('Host String: %%%% is not valid')
        self.assertEqual(response.data['detail'], e_msg)
     
    def test_put_invalid_host_string2(self):
        
        # edit nfs-export with empty host_str  
        nfs_id = 1  
        data = {'shares': ('share5', ),'host_str': '',  'mod_choice': 'rw', 'sync_choice': 'async'}
        response = self.client.put('%s/%d' % (self.BASE_URL, nfs_id), data=data)
        self.assertEqual(response.status_code,
                         status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response.data)
        e_msg = ('Cannot export without host string')
        self.assertEqual(response.data['detail'], e_msg)
            
    def test_put_invalid_admin_host1(self):  
      
        # edit nfs-export with invalid admin_host 
        nfs_id = 1  
        data = {'shares': ('share6', ), 'host_str': '*.test.co.uk', 'admin_host':'###', 'mod_choice': 'rw', 'sync_choice': 'async'}
        response = self.client.put('%s/%d' % (self.BASE_URL, nfs_id), data=data)
        self.assertEqual(response.status_code,
                         status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response.data)
        e_msg = ('Admin host: ### is not valid')
        self.assertEqual(response.data['detail'], e_msg)
    
    def test_put_invalid_admin_host2(self):  
      
        # edit nfs-export with invalid admin_host 
        nfs_id = 1  
        data = {'shares': ('share6', ), 'host_str': '*.test.co.uk', 'admin_host':'1234', 'mod_choice': 'rw', 'sync_choice': 'async'}
        response = self.client.put('%s/%d' % (self.BASE_URL, nfs_id), data=data)
        self.assertEqual(response.status_code,
                         status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response.data)
        e_msg = ('Admin host: 1234 is not valid')
        self.assertEqual(response.data['detail'], e_msg)
        
    def test_put_invalid_admin_host3(self):  
      
        # edit nfs-export with invalid admin_host 
        nfs_id = 1  
        data = {'shares': ('share6', ), 'host_str': '*.test.co.uk', 'admin_host':'rocky', 'mod_choice': 'rw', 'sync_choice': 'async'}
        response = self.client.put('%s/%d' % (self.BASE_URL, nfs_id), data=data)
        self.assertEqual(response.status_code,
                         status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response.data)
        e_msg = ('Admin host: rocky is not valid')
        self.assertEqual(response.data['detail'], e_msg)  
        
          
    def test_invalid_delete_requests(self):
        
        # deleted nfs-export that does not exist
        nfs_id = 5
        response = self.client.delete('%s/%d' % (self.BASE_URL, nfs_id))
        self.assertEqual(response.status_code,
                         status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response.data)
        e_msg = ('NFS export for the id(5) does not exist')
        self.assertEqual(response.data['detail'], e_msg)  
        
    def test_delete_requests(self):                     
        # happy path
        nfs_id = 3
        response = self.client.delete('%s/%d' % (self.BASE_URL, nfs_id))
        self.assertEqual(response.status_code,
                         status.HTTP_200_OK, msg=response.data)
