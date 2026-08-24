window.dash_clientside = Object.assign({}, window.dash_clientside, {
  clientside: {
    /** Bind Mapbox GL `click` on Plotly Scattermapbox so Dash sees map-background picks. */
    installWaterSourceMapClickRelay: function (_figure, _activeTab) {
      var dc = window.dash_clientside;
      try {
        if (!dc || typeof dc.set_props !== "function") {
          return dc.no_update;
        }
        var wrap = document.getElementById("water-source-location-map");
        if (!wrap) {
          return dc.no_update;
        }
        var gd =
          wrap.getElementsByClassName("plotly-graph-div")[0] ||
          wrap.querySelector(".js-plotly-plot");
        if (!gd || !gd._fullLayout) {
          return dc.no_update;
        }

        function isLikelyMapboxMap(obj) {
          return (
            obj &&
            typeof obj.on === "function" &&
            typeof obj.project === "function"
          );
        }

        function findMapboxGlMap(plotDiv) {
          try {
            var layout = plotDiv._fullLayout || {};
            var keys = Object.keys(layout).filter(function (k) {
              var L = layout[k];
              return L && L._subplot && k.slice(0, 7) === "mapbox";
            });
            if (layout.mapbox && keys.indexOf("mapbox") < 0) {
              keys.unshift("mapbox");
            }
            var names = ["map", "mapboxMap", "_map", "mapbox"];
            var i, j, mb, sp, m;
            for (i = 0; i < keys.length; i++) {
              mb = layout[keys[i]];
              if (!mb || !mb._subplot) continue;
              sp = mb._subplot;
              for (j = 0; j < names.length; j++) {
                m = sp[names[j]];
                if (isLikelyMapboxMap(m)) return m;
              }
              if (isLikelyMapboxMap(sp)) return sp;
            }
          } catch (eFind) {}
          return null;
        }

        function wireMap(map) {
          if (!map) return;
          if (map.__marWaterSourceClickRelay) {
            try {
              map.off("click", map.__marWaterSourceClickRelay);
            } catch (eOff) {}
          }
          map.__marWaterSourceClickRelay = function (e) {
            try {
              if (!e || !e.lngLat) return;
              dc.set_props("water-source-map-mapbox-click-store", {
                data: {
                  lat: e.lngLat.lat,
                  lon: e.lngLat.lng,
                  nonce: Date.now(),
                },
              });
            } catch (eSet) {}
          };
          map.on("click", map.__marWaterSourceClickRelay);
        }

        function tryBind() {
          var map = findMapboxGlMap(gd);
          if (map) {
            gd.__marWaterMapRelayTries = 0;
            wireMap(map);
            return true;
          }
          return false;
        }

        function scheduleBind() {
          if (gd.__marWaterRelayTimer) clearTimeout(gd.__marWaterRelayTimer);
          gd.__marWaterRelayTimer = setTimeout(function () {
            if (tryBind()) return;
            gd.__marWaterMapRelayTries = (gd.__marWaterMapRelayTries || 0) + 1;
            if (gd.__marWaterMapRelayTries < 120) scheduleBind();
          }, 120);
        }

        scheduleBind();

        var afterKey = "__marWaterAfterPlotRelay";
        if (gd[afterKey]) {
          try {
            gd.removeListener("plotly_afterplot", gd[afterKey]);
          } catch (eRm) {}
        }
        gd[afterKey] = function () {
          scheduleBind();
        };
        gd.on("plotly_afterplot", gd[afterKey]);
      } catch (eOuter) {}

      return window.dash_clientside.no_update;
    },

    resizeMapOnTab: function(topTab, optionalRunoffActiveTab) {
      if (topTab === "water-source" && optionalRunoffActiveTab === "runoff-calculator") {
        // Defer to next tick so the tab is fully visible before resizing
        setTimeout(function() {
          try {
            window.dispatchEvent(new Event("resize"));
          } catch (e) {
            // Fallback for older browsers
            var evt = document.createEvent("UIEvents");
            evt.initUIEvent("resize", true, false, window, 0);
            window.dispatchEvent(evt);
          }
        }, 0);
      }
      return window.dash_clientside.no_update;
    },

    disableAllTooltips: function() {
      disableAllTooltipsInDocument();
      return window.dash_clientside.no_update;
    }
  }
});

function disableAllTooltipsInDocument(root) {
  root = root || document;

  root.querySelectorAll("[title]").forEach(function (el) {
    var title = el.getAttribute("title");
    if (!title) return;
    if (!el.getAttribute("data-mar-title-backup")) {
      el.setAttribute("data-mar-title-backup", title);
    }
    el.removeAttribute("title");
  });

  if (typeof bootstrap !== "undefined" && bootstrap.Tooltip) {
    root.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (el) {
      try {
        var instance = bootstrap.Tooltip.getInstance(el);
        if (instance) instance.dispose();
      } catch (eDispose) {}
      el.removeAttribute("data-bs-toggle");
    });
  }
}

(function initTooltipDisabling() {
  function run() {
    disableAllTooltipsInDocument();
    if (window.__marTooltipObserver) return;
    window.__marTooltipObserver = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        mutation.addedNodes.forEach(function (node) {
          if (node && node.nodeType === 1) {
            disableAllTooltipsInDocument(node);
          }
        });
      });
    });
    window.__marTooltipObserver.observe(document.body, {
      childList: true,
      subtree: true,
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();

