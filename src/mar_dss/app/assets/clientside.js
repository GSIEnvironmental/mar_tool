function marInstallMapboxClickRelay(graphElementId, storeId, handlerKey) {
  var dc = window.dash_clientside;
  try {
    if (!dc || typeof dc.set_props !== "function") {
      return;
    }

    var wrapTimerKey = "__marMapRelayWrapTimer_" + handlerKey;
    var wrapTryKey = "__marMapRelayWrapTries_" + handlerKey;
    var maxTries = 200;

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
      if (!map) return false;
      var dblKey = handlerKey + "Dbl";
      if (map[handlerKey]) {
        try {
          map.off("click", map[handlerKey]);
        } catch (eOff) {}
      }
      if (map[dblKey]) {
        try {
          map.off("dblclick", map[dblKey]);
        } catch (eOffDbl) {}
      }
      function placeFromEvent(e) {
        try {
          if (!e || !e.lngLat) return;
          // Prefer stopping Mapbox double-click zoom so placement matches single click.
          if (e.originalEvent) {
            try {
              e.originalEvent.preventDefault();
              e.originalEvent.stopPropagation();
            } catch (ePrev) {}
          }
          if (typeof e.preventDefault === "function") {
            try {
              e.preventDefault();
            } catch (ePrev2) {}
          }
          dc.set_props(storeId, {
            data: {
              lat: e.lngLat.lat,
              lon: e.lngLat.lng,
              nonce: Date.now(),
            },
          });
        } catch (eSet) {}
      }
      map[handlerKey] = placeFromEvent;
      map[dblKey] = placeFromEvent;
      map.on("click", map[handlerKey]);
      map.on("dblclick", map[dblKey]);
      try {
        // Disable Mapbox double-click zoom so dblclick places the marker instead.
        if (typeof map.doubleClickZoom === "object" && map.doubleClickZoom.disable) {
          map.doubleClickZoom.disable();
        }
      } catch (eZoom) {}
      return true;
    }

    function bindOnce() {
      var wrap = document.getElementById(graphElementId);
      if (!wrap) {
        return false;
      }
      // Hidden / zero-size panes often have no Mapbox GL instance yet.
      if (wrap.offsetParent === null && wrap.getClientRects().length === 0) {
        return false;
      }

      var gd =
        wrap.getElementsByClassName("plotly-graph-div")[0] ||
        wrap.querySelector(".js-plotly-plot");
      if (!gd || !gd._fullLayout) {
        return false;
      }

      var tryKey = "__marMapRelayTries_" + handlerKey;
      var afterKey = "__marAfterPlotRelay_" + handlerKey;
      var map = findMapboxGlMap(gd);
      if (!map) {
        return false;
      }

      wireMap(map);
      gd[tryKey] = 0;

      if (gd[afterKey]) {
        try {
          gd.removeListener("plotly_afterplot", gd[afterKey]);
        } catch (eRm) {}
      }
      gd[afterKey] = function () {
        // Re-bind after Plotly rebuilds the map instance.
        window[wrapTryKey] = 0;
        scheduleBind(true);
      };
      gd.on("plotly_afterplot", gd[afterKey]);
      return true;
    }

    function scheduleBind(resetTries) {
      if (resetTries) {
        window[wrapTryKey] = 0;
      }
      if (window[wrapTimerKey]) {
        clearTimeout(window[wrapTimerKey]);
      }
      window[wrapTimerKey] = setTimeout(function () {
        if (bindOnce()) {
          window[wrapTryKey] = 0;
          return;
        }
        window[wrapTryKey] = (window[wrapTryKey] || 0) + 1;
        if (window[wrapTryKey] < maxTries) {
          scheduleBind(false);
        }
      }, 150);
    }

    // Fresh attempt whenever Dash re-invokes the clientside callback.
    scheduleBind(true);

    // Late layout passes (flex height / tab paint) often finish after first plot.
    setTimeout(function () {
      scheduleBind(true);
    }, 400);
    setTimeout(function () {
      scheduleBind(true);
    }, 1200);
  } catch (eOuter) {}
}

window.dash_clientside = Object.assign({}, window.dash_clientside, {
  clientside: {
    /** Bind Mapbox GL `click` on Plotly Scattermapbox so Dash sees map-background picks. */
    installWaterSourceMapClickRelay: function (_figure, _activeTab) {
      marInstallMapboxClickRelay(
        "water-source-location-map",
        "water-source-map-mapbox-click-store",
        "__marWaterSourceClickRelay"
      );
      return window.dash_clientside.no_update;
    },

    /** Overview project-location map: click places the red circle. */
    installOverviewMapClickRelay: function (_figure, _activeTab) {
      marInstallMapboxClickRelay(
        "location-map",
        "overview-map-mapbox-click-store",
        "__marOverviewClickRelay"
      );
      return window.dash_clientside.no_update;
    },

    resizeMapOnTab: function(topTab, optionalRunoffActiveTab) {
      if (topTab === "overview") {
        // Mapbox often finishes init after the Overview pane is painted.
        setTimeout(function () {
          marInstallMapboxClickRelay(
            "location-map",
            "overview-map-mapbox-click-store",
            "__marOverviewClickRelay"
          );
        }, 0);
        setTimeout(function () {
          marInstallMapboxClickRelay(
            "location-map",
            "overview-map-mapbox-click-store",
            "__marOverviewClickRelay"
          );
          try {
            window.dispatchEvent(new Event("resize"));
          } catch (eResize) {}
        }, 250);
      }
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

    attemptCloseBrowserTab: function(n_clicks) {
      if (!n_clicks) {
        return window.dash_clientside.no_update;
      }
      try {
        window.open("", "_self");
        window.close();
      } catch (eClose) {}
      setTimeout(function () {
        if (!window.closed) {
          document.body.innerHTML =
            '<div style="font-family:Segoe UI,sans-serif;padding:3rem;text-align:center;">' +
            "<h2>MAR DSS closed</h2>" +
            "<p>You may close this browser tab.</p>" +
            "</div>";
        }
      }, 250);
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

