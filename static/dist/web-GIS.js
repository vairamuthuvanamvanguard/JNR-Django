var mapId = document.getElementById("map");
function fullScreenView() {
  if (document.fullscreenElement) {
    document.exitFullscreen();
  } else {
    mapId.requestFullscreen();
  }
}

//Leaflet browser print function
L.control.browserPrint({ position: "topright" }).addTo(map);

//Leaflet search
L.Control.geocoder().addTo(map);

//Leaflet measure
L.control
  .measure({
    primaryLengthUnit: "kilometers",
    secondaryLengthUnit: "meter",
    primaryAreaUnit: "sqmeters",
    secondaryAreaUnit: undefined,
  })
  .addTo(map);

// zoom layer for the view
$(".zoom-to-layer").click(function () {
  map.setView([21.0, 78.0], 5);
});
