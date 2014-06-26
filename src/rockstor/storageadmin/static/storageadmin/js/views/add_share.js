/*
 *
 * @licstart  The following is the entire license notice for the 
 * JavaScript code in this page.
 * 
 * Copyright (c) 2012-2013 RockStor, Inc. <http://rockstor.com>
 * This file is part of RockStor.
 * 
 * RockStor is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published
 * by the Free Software Foundation; either version 2 of the License,
 * or (at your option) any later version.
 * 
 * RockStor is distributed in the hope that it will be useful, but
 * WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * General Public License for more details.
 * 
 * You should have received a copy of the GNU General Public License
 * along with this program. If not, see <http://www.gnu.org/licenses/>.
 * 
 * @licend  The above is the entire license notice
 * for the JavaScript code in this page.
 * 
 */

/*
 * Add Share View 
 */

AddShareView =  RockstorLayoutView.extend({
  events: {
    "click #js-cancel": "cancel"
  },

  initialize: function() {
    var _this = this;
    this.constructor.__super__.initialize.apply(this, arguments);
    this.template = window.JST.share_add_share_template;
   
    this.pools = new PoolCollection();
    this.pools.pageSize = RockStorGlobals.maxPageSize;
    this.poolName = this.options.poolName;
    this.dependencies.push(this.pools);
    this.numFormatter = d3.format(",.0f");
    //this.tickFormatter = function(d) {
      //var formatter = d3.format(",.2f");
      //if (d > 1024*1024) {
        //return formatter(d/(1024*1024)) + " TB";
      //} else if (d > 1024) {
        //return formatter(d/1024) + " GB";
      //} else {
        //return formatter(d) + " KB";
      //}
    //}
    this.tickFormatter = function(d) {
      return _this.numFormatter(d);
    }
    this.slider = null;
    this.sliderCallback = function(slider) {
      var value = slider.value();
      _this.$('#share_size').val(_this.tickFormatter(value));
    }
    this.tickValues = null; this.stepValues = null;
  },
  
  render: function() {

    var _this = this;
    this.pools.fetch({
      success: function(collection, response) {
        $(_this.el).append(_this.template({pools: _this.pools, poolName: _this.poolName}));

        $('#add-share-form :input').tooltip({placement: 'right'});

        _this.renderSlider();

        $('#pool_name').change(function(){
          _this.renderSlider();
        });

        $("#share_size").change(function(){
        _this.renderSlider();
          var size = this.value;
          var sizeFormat = size.replace(/[^a-z]/gi, ""); 

          var size_array = size.split(sizeFormat)
          var size_value = size_array[0];

          if(sizeFormat == 'TB' || sizeFormat == 'tb' || sizeFormat == 'Tb') {
            size_value = size_value*1024*1024;
            _this.slider.setValue(parseInt(size)*1024*1024);
          } else if (sizeFormat == 'GB' || sizeFormat == 'gb'
            || sizeFormat == 'Gb') {
            _this.slider.setValue(parseInt(size)*1024);
          } else {
            _this.slider.setValue(parseInt(size));
          }
        });

        $('#add-share-form').validate({
          onfocusout: false,
          onkeyup: false,
          rules: {
            share_name: 'required',
            share_size: {
              required: true,

            },
          },
          errorPlacement: function(error, element) {
            if (element.attr("name") == "share_size") {
              // insert error for share size after the size format field.
              error.insertAfter("#size_format");
            } else {
              error.insertAfter(element);
            }
          },

          submitHandler: function() {
            var button = _this.$('#create_share');
            if (buttonDisabled(button)) return false;
            disableButton(button);
            var share_name = $('#share_name').val();
            var pool_name = $('#pool_name').val();
            var size = $('#share_size').val();
            var sizeFormat = size.replace(/[^a-z]/gi, ""); 
            var size_array = size.split(sizeFormat)
            var size = size_array[0];

            if(sizeFormat == 'GB' || sizeFormat == 'gb' || sizeFormat == 'Gb'){
              size = size*1024*1024;
            }else if(sizeFormat == 'TB' || sizeFormat == 'tb' || sizeFormat == 'Tb'){
              size = size*1024*1024*1024;
            }

            $.ajax({
              url: "/api/shares",
              type: "POST",
              dataType: "json",
              data: {sname: share_name, "pool": pool_name, "size": size},
              success: function() {
                enableButton(button);
                _this.$('#add-share-form :input').tooltip('hide');
                app_router.navigate('shares', {trigger: true})
              },
              error: function(xhr, status, error) {
                enableButton(button);
              },
            });
          }
        });
      }
    });
    return this;
  },

  renderSlider: function(){  
    if (this.slider) {
      this.slider.destroy();
    }
    
    // Get size of selected pool
    var pool_name = this.$('#pool_name').val();
    var selectedPool = this.pools.find(function(p) { return p.get('name') == pool_name; });
    console.log('selectedPool size is ' + selectedPool.get('size'));
    var maxShareSize =  Math.floor((selectedPool.get('size')- selectedPool.get('usage'))/(1024*1024));
    console.log('maxShareSize in GB is ' + maxShareSize);
   
    var tmp = this.genTicksForShareSize(1, maxShareSize);
    this.tickValues = tmp[0]; this.stepValues = tmp[1];
    this.slider = d3.slider().min(1).max(this.tickValues[this.tickValues.length-1]).tickValues(this.tickValues).stepValues(this.stepValues).tickFormat(this.tickFormatter).callback(this.sliderCallback).showRange(true);
    d3.select('#slider').call(this.slider);

  },

  cancel: function(event) {
    event.preventDefault();
    this.$('#add-share-form :input').tooltip('hide');
    app_router.navigate('shares', {trigger: true})
  },

  /* Tick and step values
   * Max size
   * < 10 GB            - tick values every 1GB, steps at 1GB
   * 10GB  - 100 GB     - tick values every 10GB, steps at 5GB
   * 100GB - 200GB      - tick values every 20GB, steps at 10GB
   * 200GB - 300GB      - tick values every 50GB, steps at 10GB
   * 300GB - 400GB      - tick values every 50GB, steps at 10GB
   * 400GB - 500GB      - tick values every 50GB, steps at 10GB
   * 500GB - 1000GB     - tick values every 100GB, steps at 10GB
   * 1000GB - 2000GB    - tick values every 100GB, steps at 10GB
   * > 2000GB           - tick values every 200GB, steps at 10GB
   *
   */
  genTicksForShareSize: function(min, max) {
    var tickValues=[], snapValues=[], tickStep, snapStep;
    // Assume inputs are in GB
    // convert min and max to nearest multiples of 10
    var tMin = min;
    var tMax = max;
    if ((max - min) > 20) {
      tMin = Math.ceil10(min, 1);
      tMax = Math.floor10(max, 1);
    }
    console.log(tMax);
    var range = tMax - tMin;
    console.log('range is ' + range);
    if (range <= 10) {
      snapStep = 1;
      tickStep = 1;
    } else if (range <= 100) {
      snapStep = 5;
      tickStep = 10;
    } else if (range <= 500) {
      snapStep = 10;
      tickStep = 50;
    } else if (range <= 1000) {
      snapStep = 10;
      tickStep = 100;
    } else if (range <= 2000) {
      snapStep = 10;
      tickStep = 200;
    } else if (2000 < range) {
      snapStep = 10;
      tickStep = 500;
    }
    
    for (var i=0; i<= tMax; i+=snapStep) {
      snapValues.push(i==0 ? 1 : i);
    }
    for (var i=0; i<= tMax; i+=tickStep) {
      tickValues.push(i==0 ? 1 : i);
    }
    console.log(snapValues);
    console.log(tickValues);
    return [tickValues, snapValues];
  },

  getHumanizedSizeAndUnits: function(size) {
    var units = ['bytes', 'KB', 'Kb', 'MB', 'Mb', 'GB', 'Gb',
      'TB', 'Tb', 'PB', 'Pb'];
    var s = humanize.filesize(size);
    var l = 0, unit = null, num = null;
    _.each(units, function(u) {
      if (s.indexOf((u)) != -1) {
        l = u.length;
        num = s.substring(0, s.length-l);
        unit = s.substring(s.length-l);
      }
    });
    console.log(num);
    console.log(unit);
    return [num, unit];
  },


});

