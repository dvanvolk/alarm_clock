const CONDITION_LABELS = {
  "clear-night":     "Clear",
  "cloudy":          "Cloudy",
  "fog":             "Foggy",
  "hail":            "Hail",
  "lightning":       "Thunderstorm",
  "lightning-rainy": "Stormy",
  "partlycloudy":    "Partly Cloudy",
  "pouring":         "Heavy Rain",
  "rainy":           "Rain",
  "snowy":           "Snow",
  "snowy-rainy":     "Sleet",
  "sunny":           "Sunny",
  "windy":           "Windy",
  "windy-variant":   "Windy",
  "exceptional":     "Unusual",
};

function handleWeatherUpdate(msg) {
  const el     = document.getElementById("weather");
  const condEl = document.getElementById("weather-condition");
  const tempEl = document.getElementById("weather-temp");
  const hlEl   = document.getElementById("weather-high-low");

  if (msg.condition != null) {
    condEl.textContent = CONDITION_LABELS[msg.condition] ?? msg.condition;
  }
  if (msg.temp != null) {
    tempEl.textContent = `${msg.temp}°`;
  }
  if (msg.high != null && msg.low != null) {
    hlEl.textContent = `H:${Math.round(msg.high)}°  L:${Math.round(msg.low)}°`;
  }

  el.classList.remove("hidden");
}
