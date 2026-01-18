const MAP_ID = "95d18bf62fd3f65236e9811e";
const MAP_TILT = 0;
const MAP_STYLE = [
  {
    elementType: "geometry",
    stylers: [{ color: "#f2e9df" }],
  },
  {
    elementType: "labels.text.fill",
    stylers: [{ color: "#6d5c4c" }],
  },
  {
    elementType: "labels.text.stroke",
    stylers: [{ color: "#f2e9df" }],
  },
  {
    featureType: "water",
    elementType: "geometry",
    stylers: [{ color: "#d5e5f1" }],
  },
  {
    featureType: "poi.park",
    elementType: "geometry",
    stylers: [{ color: "#dfe9d4" }],
  },
  {
    featureType: "road",
    elementType: "geometry",
    stylers: [{ color: "#f7f0e8" }],
  },
  {
    featureType: "road",
    elementType: "labels.text.fill",
    stylers: [{ color: "#9a8a7a" }],
  },
];

const houses = [
  {
    id: 1,
    title: "Hammock Bay Villa",
    location: "Oak Harbor, Stockholm County",
    price: "$1,250,000",
    beds: 4,
    baths: 3,
    area: "210 m2",
    year: 2018,
    image: "assets/house-placeholder.svg",
    features: [
      "Dock access with sunset views",
      "Heated stone floors",
      "Glass atrium kitchen",
      "Guest studio + sauna",
    ],
    lat: 59.33258,
    lng: 18.0649,
  },
  {
    id: 2,
    title: "Vinterhamn Loft",
    location: "Sodermalm, Stockholm",
    price: "$980,000",
    beds: 3,
    baths: 2,
    area: "155 m2",
    year: 2014,
    image: "assets/house-placeholder.svg",
    features: [
      "Brick arches + skylights",
      "Walkable waterfront",
      "Custom oak cabinetry",
      "Private rooftop terrace",
    ],
    lat: 59.315,
    lng: 18.07,
  },
  {
    id: 3,
    title: "Nordic Pines Retreat",
    location: "Nacka Nature Reserve",
    price: "$1,640,000",
    beds: 5,
    baths: 4,
    area: "260 m2",
    year: 2021,
    image: "assets/house-placeholder.svg",
    features: [
      "Architectural cedar facade",
      "Infinity plunge pool",
      "Smart glass walls",
      "Forest trail access",
    ],
    lat: 59.296,
    lng: 18.166,
  },
  {
    id: 4,
    title: "Gamla Stan Jewel",
    location: "Old Town, Stockholm",
    price: "$870,000",
    beds: 2,
    baths: 1,
    area: "98 m2",
    year: 1890,
    image: "assets/house-placeholder.svg",
    features: [
      "Original timber beams",
      "Boutique courtyard",
      "Chef-ready galley",
      "Private wine nook",
    ],
    lat: 59.3258,
    lng: 18.0703,
  },
];

let map;
let markers = [];
let activeIndex = 0;

const listingTitle = document.getElementById("listing-title");
const listingLocation = document.getElementById("listing-location");
const listingPrice = document.getElementById("listing-price");
const listingBeds = document.getElementById("listing-beds");
const listingBaths = document.getElementById("listing-baths");
const listingArea = document.getElementById("listing-area");
const listingYear = document.getElementById("listing-year");
const listingImage = document.getElementById("listing-image");
const listingFeatures = document.getElementById("listing-features");
const mapOverlay = document.getElementById("map-overlay");

function updateListing(house) {
  listingTitle.textContent = house.title;
  listingLocation.textContent = house.location;
  listingPrice.textContent = house.price;
  listingBeds.textContent = house.beds;
  listingBaths.textContent = house.baths;
  listingArea.textContent = house.area;
  listingYear.textContent = house.year;
  listingImage.src = house.image;
  listingImage.alt = house.title;

  listingFeatures.innerHTML = "";
  house.features.forEach((feature) => {
    const item = document.createElement("li");
    item.textContent = feature;
    listingFeatures.appendChild(item);
  }); 
}

function markerIcon(isActive) {
  return {
    path: google.maps.SymbolPath.CIRCLE,
    scale: isActive ? 10 : 7,
    fillColor: isActive ? "#1f2a2e" : "#d77b4b",
    fillOpacity: 1,
    strokeColor: "#fff3e7",
    strokeWeight: 2,
  };
}

function selectHouse(index) {
  const house = houses[index];
  activeIndex = index;
  updateListing(house);

  markers.forEach((marker, markerIndex) => {
    marker.setIcon(markerIcon(markerIndex === index));
  });

  if (map) {
    map.panTo({ lat: house.lat, lng: house.lng });
  }
}

function initMap() {
  if (!window.google || !google.maps) {
    return;
  }

  map = new google.maps.Map(document.getElementById("map"), {
    center: { lat: houses[0].lat, lng: houses[0].lng },
    zoom: 16,
    mapId: MAP_ID,
    tilt: MAP_TILT,
    mapTypeId: "roadmap",
    styles: MAP_STYLE,
    disableDefaultUI: false,
    zoomControl: true,
  });

  google.maps.event.addListenerOnce(map, "idle", () => {
    map.setTilt(MAP_TILT);
    const appliedMapId = map.get("mapId");
    if (appliedMapId !== MAP_ID) {
      console.warn("Map ID not applied:", appliedMapId);
    }
  });

  markers = houses.map((house, index) => {
    const marker = new google.maps.Marker({
      position: { lat: house.lat, lng: house.lng },
      map,
      title: house.title,
      icon: markerIcon(index === activeIndex),
    });

    marker.addListener("click", () => {
      selectHouse(index);
    });

    return marker;
  });

  mapOverlay.classList.add("hidden");
  selectHouse(activeIndex);
}

document.addEventListener("DOMContentLoaded", () => {
  updateListing(houses[0]);
});

window.initMap = initMap;
