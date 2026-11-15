// Icon dictionary for templates: emoji grouped by meaning, each with English
// and Romanian keywords so the picker's search works in both languages.
// Rendering is the OS emoji font — nothing to ship, nothing to license.
//
// The validity check mirrors app/utils/icons.py: at least one pictographic
// symbol, and no letters / digits / "?" (which is what mojibake like "âš¡"
// or a lost "??" look like).

export const ICON_GROUPS = [
  { id: "status", icons: [
    ["✅", "ok check done success", "ok bifă gata succes"],
    ["⚠️", "warning caution", "avertizare atenție"],
    ["❌", "error fail cross", "eroare eșec"],
    ["⛔", "stop blocked forbidden", "stop blocat interzis"],
    ["🚨", "alarm siren critical emergency", "alarmă sirenă critic urgență"],
    ["🔴", "red critical down", "roșu critic căzut"],
    ["🟠", "orange high", "portocaliu ridicat"],
    ["🟡", "yellow medium", "galben mediu"],
    ["🟢", "green ok up online", "verde ok pornit online"],
    ["🔵", "blue info", "albastru informare"],
    ["❓", "unknown question", "necunoscut întrebare"],
    ["🔔", "bell notify notification", "clopot notificare"],
    ["🔕", "mute silence quiet", "silențios liniște"],
    ["⏸️", "pause paused", "pauză"],
    ["▶️", "resume start play", "reluare pornire"],
    ["🔁", "repeat retry loop", "repetă reîncercare"],
    ["🔄", "restart reboot refresh", "repornire reboot"],
  ]},
  { id: "energy", icons: [
    ["⚡", "power electricity voltage lightning", "putere electricitate tensiune"],
    ["🔌", "plug grid connection", "priză conexiune rețea"],
    ["🔋", "battery charge storage", "baterie încărcare stocare"],
    ["🪫", "battery low empty discharged", "baterie descărcată goală"],
    ["☀️", "sun solar pv production", "soare solar fotovoltaic producție"],
    ["🌤️", "partly sunny", "parțial însorit"],
    ["🏭", "grid utility factory", "rețea furnizor fabrică"],
    ["💡", "light consumption load", "lumină consum sarcină"],
    ["📈", "rise increase production up", "creștere producție sus"],
    ["📉", "drop decrease down", "scădere jos"],
    ["⚖️", "balance contract limit", "echilibru contract limită"],
    ["💰", "money cost price", "bani cost preț"],
    ["💶", "euro tariff price", "euro tarif preț"],
    ["🔆", "irradiance brightness", "iradiere luminozitate"],
  ]},
  { id: "infra", icons: [
    ["🖥️", "server host computer", "server gazdă calculator"],
    ["💻", "computer laptop", "calculator laptop"],
    ["🐳", "docker container", "docker container"],
    ["📦", "package container image", "pachet container imagine"],
    ["💾", "disk storage save", "disc stocare salvare"],
    ["🗄️", "database storage archive", "bază de date arhivă"],
    ["🌐", "network internet web", "rețea internet web"],
    ["📡", "antenna signal radio", "antenă semnal radio"],
    ["📶", "signal strength lte", "semnal putere lte"],
    ["🔗", "link connection", "legătură conexiune"],
    ["⚙️", "settings config gear", "setări configurare"],
    ["🛠️", "maintenance tools repair", "mentenanță unelte reparație"],
    ["🔧", "wrench fix", "cheie reparație"],
    ["🧰", "toolbox service", "trusă service"],
    ["🔒", "lock security locked", "lacăt securitate blocat"],
    ["🔓", "unlock open", "deblocat deschis"],
    ["🔑", "key credential", "cheie credențial"],
    ["🛡️", "shield protection", "scut protecție"],
  ]},
  { id: "environment", icons: [
    ["🌡️", "temperature thermal heat", "temperatură termic căldură"],
    ["🔥", "fire hot overheat", "foc fierbinte supraîncălzire"],
    ["❄️", "cold frost freeze cooling", "frig îngheț răcire"],
    ["💧", "water humidity leak", "apă umiditate scurgere"],
    ["🌧️", "rain", "ploaie"],
    ["⛈️", "storm thunder", "furtună tunet"],
    ["🌬️", "wind", "vânt"],
    ["💨", "air fan ventilation", "aer ventilator ventilație"],
    ["☁️", "cloud cloudy", "nor înnorat"],
    ["🌫️", "fog", "ceață"],
    ["🌙", "night moon", "noapte lună"],
    ["🌅", "sunrise morning", "răsărit dimineață"],
    ["🌇", "sunset evening", "apus seară"],
  ]},
  { id: "time", icons: [
    ["⏰", "alarm clock deadline", "ceas alarmă termen"],
    ["⏱️", "timer stopwatch latency", "cronometru latență"],
    ["⏳", "waiting stale timeout", "așteptare vechi expirat"],
    ["🕒", "time schedule", "timp program"],
    ["📅", "calendar date daily", "calendar dată zilnic"],
    ["📊", "chart stats report summary", "grafic statistici raport rezumat"],
    ["📋", "list report checklist", "listă raport"],
    ["📝", "note log", "notă jurnal"],
    ["🧾", "invoice receipt bill", "factură chitanță"],
    ["🗂️", "data files", "date fișiere"],
  ]},
  { id: "communication", icons: [
    ["✉️", "email mail", "email mail"],
    ["📨", "message incoming", "mesaj primit"],
    ["💬", "chat telegram message", "chat telegram mesaj"],
    ["📱", "phone sms mobile", "telefon sms mobil"],
    ["☎️", "call voice", "apel voce"],
    ["📣", "announce broadcast", "anunț difuzare"],
  ]},
  { id: "places", icons: [
    ["🏠", "home house", "casă locuință"],
    ["🏢", "building office", "clădire birou"],
    ["🚪", "door access", "ușă acces"],
    ["🚗", "car ev vehicle", "mașină vehicul electric"],
    ["🚚", "truck delivery", "camion livrare"],
    ["👤", "user person", "utilizator persoană"],
    ["👥", "users team", "utilizatori echipă"],
    ["🧑‍🔧", "technician operator", "tehnician operator"],
    ["🧯", "extinguisher safety", "extinctor siguranță"],
    ["🧪", "test experiment", "test experiment"],
    ["🎯", "target goal", "țintă obiectiv"],
    ["🚀", "launch deploy start", "lansare deploy pornire"],
    ["🎉", "celebrate success", "sărbătoare succes"],
  ]},
];

// The server's rule (app/utils/icons.py), character class for character class:
// no letter, digit, "?" or "�" (mojibake, a lost emoji), and at least one
// "other symbol" (So). tests/js/support/icon_parity.json keeps the two equal.
const TEXT = /[\p{L}\p{N}?�]/u;
const SYMBOL = /\p{So}/u;

// "" → valid (no icon); otherwise an emoji, never text or mojibake.
export function isValidIcon(value) {
  const v = (value || "").trim();
  if (!v) return true;
  return SYMBOL.test(v) && !TEXT.test(v);
}

// Flat list filtered by a free-text query over both keyword languages.
export function searchIcons(query) {
  const q = (query || "").trim().toLowerCase();
  const out = [];
  for (const g of ICON_GROUPS) {
    for (const [emoji, en, ro] of g.icons) {
      if (!q || en.includes(q) || ro.includes(q) || emoji === q) out.push({ group: g.id, emoji, name: en.split(" ")[0] });
    }
  }
  return out;
}
