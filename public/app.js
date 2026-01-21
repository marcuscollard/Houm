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

const defaultCenter = { lat: 59.3293, lng: 18.0686 };
const listingCache = new Map();
const markersById = new Map();
let listingPoints = [];
let activeListingId = null;
let profileName = "";
const favoriteIds = new Set();
const recommendedIds = new Set();
const recommendationNotes = new Map();
let openProfileDialog = null;

let map;
let markers = [];

const listingTitle = document.getElementById("listing-title");
const listingLocation = document.getElementById("listing-location");
const listingPrice = document.getElementById("listing-price");
const listingBeds = document.getElementById("listing-beds");
const listingBaths = document.getElementById("listing-baths");
const listingArea = document.getElementById("listing-area");
const listingYear = document.getElementById("listing-year");
const listingImage = document.getElementById("listing-image");
const listingFeatures = document.getElementById("listing-features");
const listingPros = document.getElementById("listing-pros");
const listingCons = document.getElementById("listing-cons");
const mapOverlay = document.getElementById("map-overlay");
const mapStatus = document.getElementById("map-status");
const saveFavoriteButton = document.getElementById("save-favorite");
const mapQuery = document.getElementById("map-query");
const mapQueryToggle = document.getElementById("map-query-toggle");
const mapQueryHistory = document.getElementById("map-query-history");
const mapQueryForm = document.getElementById("map-query-form");
const mapQueryInput = document.getElementById("map-query-input");
let lastBbox = null;
let pointsLoading = false;
const mapQueryStorageKey = "houmMapQueryHistory";
let mapQueryInitialized = false;

const apiBase =
  typeof document !== "undefined" ? document.body?.dataset.apiBase || "" : "";
const apiBaseNormalized = apiBase.replace(/\/$/, "");

function apiUrl(path) {
  if (!path || typeof path !== "string") {
    return path;
  }
  if (path.startsWith("http") || !apiBaseNormalized) {
    return path;
  }
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${apiBaseNormalized}${normalized}`;
}

function resolveApiAssetUrl(url) {
  if (!url || typeof url !== "string") {
    return url;
  }
  if (url.startsWith("http") || url.startsWith("data:")) {
    return url;
  }
  if (url.startsWith("/") && apiBaseNormalized) {
    return `${apiBaseNormalized}${url}`;
  }
  return url;
}

const numberFormatter = new Intl.NumberFormat("sv-SE");

function formatSek(value) {
  if (value === null || value === undefined) {
    return "—";
  }
  return `${numberFormatter.format(value)} kr`;
}

function formatRooms(value) {
  if (value === null || value === undefined) {
    return "—";
  }
  return numberFormatter.format(value);
}

function formatArea(listing) {
  if (listing.formatted_living_area) {
    return listing.formatted_living_area;
  }
  if (listing.square_meters) {
    return `${numberFormatter.format(listing.square_meters)} m2`;
  }
  return "—";
}

function updateFavoriteButton() {
  if (!saveFavoriteButton) {
    return;
  }
  if (!activeListingId) {
    saveFavoriteButton.disabled = true;
    saveFavoriteButton.classList.remove("is-saved");
    saveFavoriteButton.textContent = "Save";
    return;
  }
  saveFavoriteButton.disabled = false;
  if (profileName && favoriteIds.has(activeListingId)) {
    saveFavoriteButton.classList.add("is-saved");
    saveFavoriteButton.textContent = "Saved";
  } else {
    saveFavoriteButton.classList.remove("is-saved");
    saveFavoriteButton.textContent = "Save";
  }
  refreshMarkerIcons();
}

async function syncProfile(name, preferences) {
  const payload = { name };
  if (preferences && typeof preferences === "object") {
    payload.preferences = preferences;
  }
  const response = await fetch(apiUrl("/api/profile"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Profile request failed.");
  }
  const data = await response.json();
  favoriteIds.clear();
  (data.favorites || []).forEach((hemnetId) => favoriteIds.add(Number(hemnetId)));
  updateFavoriteButton();
  return data;
}

async function addFavorite(hemnetId) {
  const response = await fetch(apiUrl("/api/favorites"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: profileName, hemnet_id: hemnetId }),
  });
  if (!response.ok) {
    throw new Error("Favorite request failed.");
  }
  const data = await response.json();
  favoriteIds.clear();
  (data.favorites || []).forEach((id) => favoriteIds.add(Number(id)));
  updateFavoriteButton();
}

async function removeFavorite(hemnetId) {
  const response = await fetch(apiUrl("/api/favorites"), {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: profileName, hemnet_id: hemnetId }),
  });
  if (!response.ok) {
    throw new Error("Favorite request failed.");
  }
  const data = await response.json();
  favoriteIds.clear();
  (data.favorites || []).forEach((id) => favoriteIds.add(Number(id)));
  updateFavoriteButton();
}

function extractFeatures(listing) {
  const features = [];
  const labels = listing.labels || [];
  const amenities = listing.relevant_amenities || [];

  if (Array.isArray(labels)) {
    labels.forEach((label) => {
      if (label && label.text) {
        features.push(label.text);
      }
    });
  }

  if (Array.isArray(amenities)) {
    amenities.forEach((amenity) => {
      if (amenity && amenity.title) {
        features.push(amenity.title);
      }
    });
  }

  if (listing.housing_form) {
    features.push(listing.housing_form);
  }
  if (listing.tenure) {
    features.push(listing.tenure);
  }

  return [...new Set(features)].slice(0, 6);
}

function updateListing(listing) {
  if (!listing) {
    return;
  }

  listingTitle.textContent = listing.title || listing.address || "Listing";
  listingLocation.textContent =
    listing.geographic_area ||
    listing.municipality_name ||
    listing.region_name ||
    "—";
  listingPrice.textContent = formatSek(listing.price || listing.asked_price);
  listingBeds.textContent = formatRooms(listing.rooms);
  listingBaths.textContent = formatSek(listing.monthly_fee);
  listingArea.textContent = formatArea(listing);
  listingYear.textContent = listing.year || "—";
  const rawImageUrl =
    listing.image_url || listing.main_image_url || "assets/house-placeholder.svg";
  listingImage.src = resolveApiAssetUrl(rawImageUrl);
  listingImage.alt = listing.title || listing.address || "Listing";

  listingFeatures.innerHTML = "";
  extractFeatures(listing).forEach((feature) => {
    const item = document.createElement("li");
    item.textContent = feature;
    listingFeatures.appendChild(item);
  });

  updateRecommendationNotes(listing.hemnet_id);
}

function markerIcon({ isActive, isSaved, isRecommended }) {
  const fillColor = isActive
    ? "#1f2a2e"
    : isRecommended
      ? "#0f6d3a"
      : isSaved
        ? "#2f7ff2"
        : "#d77b4b";
  const scale = isActive ? 12 : 9;
  return {
    path: google.maps.SymbolPath.CIRCLE,
    scale,
    fillColor,
    fillOpacity: 1,
    strokeColor: "#fff3e7",
    strokeWeight: 2,
  };
}

function setActiveMarker(hemnetId) {
  activeListingId = hemnetId;
  refreshMarkerIcons();
}

function refreshMarkerIcons() {
  if (!map) {
    return;
  }
  markersById.forEach((marker, markerId) => {
    marker.setIcon(
      markerIcon({
        isActive: markerId === activeListingId,
        isSaved: favoriteIds.has(markerId),
        isRecommended: recommendedIds.has(markerId),
      })
    );
  });
}

async function fetchListing(hemnetId) {
  if (listingCache.has(hemnetId)) {
    return listingCache.get(hemnetId);
  }

  const response = await fetch(apiUrl(`/api/listings/${hemnetId}`), {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error("Listing request failed.");
  }
  const data = await response.json();
  listingCache.set(hemnetId, data);
  return data;
}

async function selectListing(hemnetId, options = {}) {
  if (!hemnetId) {
    return;
  }
  const { pan = true } = options;
  setActiveMarker(hemnetId);
  updateFavoriteButton();
  const marker = markersById.get(hemnetId);
  if (pan && marker && map) {
    map.panTo(marker.getPosition());
  }
  try {
    const listing = await fetchListing(hemnetId);
    updateListing(listing);
  } catch (error) {
    console.warn("Listing load failed:", error);
  }
}

function renderMarkers() {
  markers.forEach((marker) => marker.setMap(null));
  markers = [];
  markersById.clear();

  if (!map || listingPoints.length === 0) {
    return;
  }

  markers = listingPoints.map((point) => {
    const marker = new google.maps.Marker({
      position: { lat: point.lat, lng: point.lng },
      map,
      title: String(point.hemnet_id),
      icon: markerIcon({
        isActive: point.hemnet_id === activeListingId,
        isSaved: favoriteIds.has(point.hemnet_id),
        isRecommended: recommendedIds.has(point.hemnet_id),
      }),
    });

    marker.addListener("click", () => {
      selectListing(point.hemnet_id);
    });

    markersById.set(point.hemnet_id, marker);
    return marker;
  });

  mapOverlay.classList.add("hidden");
}

function setRecommendedIds(ids) {
  recommendedIds.clear();
  if (Array.isArray(ids)) {
    ids.forEach((id) => {
      const parsed = Number(id);
      if (Number.isFinite(parsed)) {
        recommendedIds.add(parsed);
      }
    });
  }
  refreshMarkerIcons();
}

function setRecommendationNotes(notesById) {
  recommendationNotes.clear();
  if (!notesById || typeof notesById !== "object") {
    return;
  }
  Object.entries(notesById).forEach(([key, value]) => {
    const parsedId = Number(key);
    if (!Number.isFinite(parsedId) || !value || typeof value !== "object") {
      return;
    }
    const pros = Array.isArray(value.pros)
      ? value.pros.filter((item) => typeof item === "string")
      : [];
    const cons = Array.isArray(value.cons)
      ? value.cons.filter((item) => typeof item === "string")
      : [];
    recommendationNotes.set(parsedId, { pros, cons });
  });
}

function updateRecommendationNotes(hemnetId) {
  if (!listingPros || !listingCons) {
    return;
  }
  listingPros.innerHTML = "";
  listingCons.innerHTML = "";
  const parsedId = Number(hemnetId);
  const notes = recommendationNotes.get(parsedId);
  if (!notes) {
    return;
  }
  notes.pros.forEach((text) => {
    const item = document.createElement("li");
    item.className = "note-positive";
    item.textContent = text;
    listingPros.appendChild(item);
  });
  notes.cons.forEach((text) => {
    const item = document.createElement("li");
    item.className = "note-negative";
    item.textContent = text;
    listingCons.appendChild(item);
  });
}

function setPoints(points) {
  listingPoints = Array.isArray(points)
    ? points.filter((point) => point && point.lat && point.lng)
    : [];
  renderMarkers();
  if (!activeListingId && listingPoints.length > 0) {
    selectListing(listingPoints[0].hemnet_id, { pan: false });
  }
}

function initMap() {
  if (!window.google || !google.maps) {
    return;
  }

  map = new google.maps.Map(document.getElementById("map"), {
    center: defaultCenter,
    zoom: 12,
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

  renderMarkers();

  map.addListener("idle", () => {
    loadPointsForMap();
  });
}

function showMapError(message) {
  if (mapStatus) {
    mapStatus.textContent = message;
  }
  if (mapOverlay) {
    mapOverlay.classList.remove("hidden");
  }
}

async function loadGoogleMaps() {
  try {
    const response = await fetch(apiUrl("/config"), { cache: "no-store" });
    if (!response.ok) {
      throw new Error("Map config request failed.");
    }

    const data = await response.json();
    const apiKey = data.googleMapsApiKey;
    if (!apiKey) {
      throw new Error("Missing Google Maps API key.");
    }

    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(
      apiKey
    )}&callback=initMap`;
    script.async = true;
    script.defer = true;
    script.onerror = () => {
      showMapError("Failed to load Google Maps.");
    };
    document.head.appendChild(script);
  } catch (error) {
    showMapError("Set GOOGLE_MAPS_API_KEY in .env and run the backend server.");
    console.warn("Map setup failed:", error);
  }
}

function boundsToBbox(bounds) {
  if (!bounds) {
    return null;
  }
  const sw = bounds.getSouthWest();
  const ne = bounds.getNorthEast();
  return `${sw.lng()},${sw.lat()},${ne.lng()},${ne.lat()}`;
}

async function loadPointsForMap() {
  if (!map || pointsLoading) {
    return;
  }
  const bbox = boundsToBbox(map.getBounds());
  if (!bbox || bbox === lastBbox) {
    return;
  }
  lastBbox = bbox;
  pointsLoading = true;
  try {
    const response = await fetch(
      apiUrl(`/api/listings/points?bbox=${encodeURIComponent(bbox)}`),
      { cache: "no-store" }
    );
    if (!response.ok) {
      throw new Error("Points request failed.");
    }
    const data = await response.json();
    setPoints(data.points || []);
  } catch (error) {
    showMapError("Listings are unavailable. Check the database connection.");
    console.warn("Points load failed:", error);
  } finally {
    pointsLoading = false;
  }
}

function initApp() {
  loadGoogleMaps();
  initProfile();
  initFavorites();
  initMapQuery();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initApp);
} else {
  initApp();
}

window.initMap = initMap;

function initProfile() {
  const profileButton = document.getElementById("profile-button");
  const profilePopover = document.getElementById("profile-popover");
  const profileForm = document.getElementById("profile-form");
  const profileNameInput = document.getElementById("profile-name-input");
  const profileGreeting = document.getElementById("profile-greeting");
  if (!profileButton || !profilePopover || !profileForm || !profileNameInput) {
    return;
  }

  const storageKey = "houmProfileName";

  const updateProfile = async (name) => {
    const trimmed = name.trim();
    profileName = trimmed;
    if (trimmed) {
      localStorage.setItem(storageKey, trimmed);
      if (profileGreeting) {
        profileGreeting.textContent = `Signed in as ${trimmed}.`;
      }
      profileButton.setAttribute("aria-label", `Profile (${trimmed})`);
      profileButton.title = trimmed;
      try {
        await syncProfile(trimmed);
      } catch (error) {
        console.warn("Profile sync failed:", error);
      }
    } else {
      localStorage.removeItem(storageKey);
      if (profileGreeting) {
        profileGreeting.textContent = "Not signed in.";
      }
      profileButton.setAttribute("aria-label", "Profile");
      profileButton.removeAttribute("title");
      favoriteIds.clear();
      updateFavoriteButton();
    }
  };

  const openProfile = () => {
    profilePopover.classList.remove("hidden");
    profileButton.setAttribute("aria-expanded", "true");
    profileNameInput.focus();
    profileNameInput.select();
  };

  const closeProfile = () => {
    profilePopover.classList.add("hidden");
    profileButton.setAttribute("aria-expanded", "false");
  };

  const storedName = localStorage.getItem(storageKey) || "";
  profileNameInput.value = storedName;
  updateProfile(storedName);

  openProfileDialog = openProfile;

  profileButton.addEventListener("click", (event) => {
    event.stopPropagation();
    if (profilePopover.classList.contains("hidden")) {
      openProfile();
    } else {
      closeProfile();
    }
  });

  profilePopover.addEventListener("click", (event) => {
    event.stopPropagation();
  });

  profileForm.addEventListener("submit", (event) => {
    event.preventDefault();
    updateProfile(profileNameInput.value);
    closeProfile();
  });

  document.addEventListener("click", () => {
    if (!profilePopover.classList.contains("hidden")) {
      closeProfile();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeProfile();
    }
  });
}

function initFavorites() {
  if (!saveFavoriteButton) {
    return;
  }
  saveFavoriteButton.addEventListener("click", async () => {
    if (!activeListingId) {
      return;
    }
    if (!profileName) {
      if (openProfileDialog) {
        openProfileDialog();
      }
      return;
    }
    try {
      if (favoriteIds.has(activeListingId)) {
        await removeFavorite(activeListingId);
      } else {
        await addFavorite(activeListingId);
      }
    } catch (error) {
      console.warn("Favorite update failed:", error);
    }
  });
  updateFavoriteButton();
}

function initMapQuery() {
  if (
    mapQueryInitialized ||
    !mapQuery ||
    !mapQueryToggle ||
    !mapQueryForm ||
    !mapQueryInput
  ) {
    return;
  }
  mapQueryInitialized = true;

  const history = loadMapQueryHistory();
  history.forEach((entry) => appendMapQueryMessage(entry.role, entry.text));

  mapQueryToggle.addEventListener("click", () => {
    const isOpen = mapQuery.classList.toggle("is-open");
    mapQueryToggle.setAttribute("aria-expanded", String(isOpen));
    mapQueryToggle.textContent = isOpen ? "Collapse" : "Expand";
  });

  mapQueryForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = mapQueryInput.value.trim();
    if (!text) {
      return;
    }
    mapQueryInput.value = "";
    appendMapQueryMessage("user", text);
    saveMapQueryHistory("user", text);
    sendMapQuery(text).catch((error) => {
      appendMapQueryMessage("assistant", "Assistant is unavailable right now.");
      console.warn("Assistant failed:", error);
    });
  });
}

function appendMapQueryMessage(role, text) {
  if (!mapQueryHistory) {
    return;
  }
  const message = document.createElement("div");
  message.className = `map-query-message ${role}`;
  message.textContent = text;
  mapQueryHistory.appendChild(message);
  mapQueryHistory.scrollTop = mapQueryHistory.scrollHeight;
}

function loadMapQueryHistory() {
  try {
    const raw = localStorage.getItem(mapQueryStorageKey);
    const data = raw ? JSON.parse(raw) : [];
    if (Array.isArray(data)) {
      return data.slice(-20);
    }
  } catch (error) {
    return [];
  }
  return [];
}

function saveMapQueryHistory(role, text) {
  const history = loadMapQueryHistory();
  history.push({ role, text });
  localStorage.setItem(mapQueryStorageKey, JSON.stringify(history.slice(-40)));
}

async function sendMapQuery(message) {
  const history = loadMapQueryHistory().slice(-6);
  const bbox = map ? boundsToBbox(map.getBounds()) : null;
  const payload = {
    message,
    history: history.map((entry) => ({
      role: entry.role,
      content: entry.text,
    })),
    context: {
      bbox,
    },
  };
  const response = await fetch(apiUrl("/api/assistant"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Assistant request failed.");
  }
  const data = await response.json();
  if (Array.isArray(data.recommended_ids)) {
    setRecommendedIds(data.recommended_ids);
  }
  setRecommendationNotes(
    data.recommendation_notes && typeof data.recommendation_notes === "object"
      ? data.recommendation_notes
      : {}
  );
  if (activeListingId) {
    updateRecommendationNotes(activeListingId);
  }
  const reply = data.reply || data.message || "No response.";
  appendMapQueryMessage("assistant", reply);
  saveMapQueryHistory("assistant", reply);
}
