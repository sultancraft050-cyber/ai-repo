from __future__ import annotations

import re
from typing import Any


GLOBAL_HARDWARE_CATEGORIES = [
    "CPU",
    "GPU",
    "Motherboard",
    "RAM",
    "PSU",
    "Case",
    "Cooler",
    "Storage",
    "Monitor",
    "Keyboard",
    "Mouse",
    "Headset",
    "Capture Card",
    "Fans",
    "Custom Cooling",
    "Accessories",
]

BUILD_CRITICAL_CATEGORIES = {
    "CPU",
    "GPU",
    "Motherboard",
    "RAM",
    "PSU",
    "Case",
    "Cooler",
    "Storage",
}

CATEGORY_ALIASES = {
    "processor": "CPU",
    "cpu": "CPU",
    "graphics card": "GPU",
    "video card": "GPU",
    "gpu": "GPU",
    "motherboard": "Motherboard",
    "mainboard": "Motherboard",
    "memory": "RAM",
    "ram": "RAM",
    "power supply": "PSU",
    "psu": "PSU",
    "pc case": "Case",
    "case": "Case",
    "cpu cooler": "Cooler",
    "aio": "Cooler",
    "air cooler": "Cooler",
    "ssd": "Storage",
    "hard drive": "Storage",
    "hdd": "Storage",
    "storage": "Storage",
    "monitor": "Monitor",
    "display": "Monitor",
    "keyboard": "Keyboard",
    "mouse": "Mouse",
    "headset": "Headset",
    "headphones": "Headset",
    "capture card": "Capture Card",
    "case fan": "Fans",
    "fans": "Fans",
    "radiator": "Custom Cooling",
    "pump reservoir": "Custom Cooling",
    "water block": "Custom Cooling",
    "custom cooling": "Custom Cooling",
    "accessory": "Accessories",
    "accessories": "Accessories",
}

CATEGORY_PATTERNS: list[tuple[str, str]] = [
    (r"\b(ryzen|core i[3579]|threadripper|xeon|processor|cpu)\b", "CPU"),
    (r"\b(rtx|gtx|radeon|geforce|rx\s?\d{4}|arc\s?[ab]\d{3}|graphics card|gpu)\b", "GPU"),
    (r"\b(x670|b650|z790|b760|x870|z890|motherboard|mainboard|mini[- ]?itx|atx board)\b", "Motherboard"),
    (r"\b(ddr[45]|sodimm|dimm|memory kit|ram)\b", "RAM"),
    (r"\b(power supply|psu|\d{3,4}\s?w\b|80\+|80 plus)\b", "PSU"),
    (r"\b(mid tower|full tower|mini[- ]?itx case|pc case|computer case)\b", "Case"),
    (r"\b(cpu cooler|liquid cooler|air cooler|aio|heatsink)\b", "Cooler"),
    (r"\b(nvme|m\.2|ssd|hdd|hard drive|solid state)\b", "Storage"),
    (r"\b(monitor|display|oled|ips|va panel|\d{2,3}\s?hz|ultrawide)\b", "Monitor"),
    (r"\b(keyboard|mechanical|switches|keycaps)\b", "Keyboard"),
    (r"\b(mouse|gaming mouse|dpi)\b", "Mouse"),
    (r"\b(headset|headphone|microphone|wireless headset)\b", "Headset"),
    (r"\b(capture card|elgato|streaming card|hd60|4k60)\b", "Capture Card"),
    (r"\b(case fan|fan pack|pwm fan|120mm fan|140mm fan)\b", "Fans"),
    (r"\b(water block|pump|reservoir|radiator|fitting|coolant|hardline|soft tubing)\b", "Custom Cooling"),
]

DISCOVERY_QUERY_TEMPLATES: dict[str, list[str]] = {
    "CPU": ["AMD Ryzen desktop processor", "Intel Core desktop processor"],
    "GPU": ["NVIDIA GeForce RTX graphics card", "AMD Radeon RX graphics card"],
    "Motherboard": ["AM5 motherboard", "LGA1700 motherboard", "DDR5 motherboard"],
    "RAM": ["DDR5 memory kit", "DDR4 memory kit"],
    "PSU": ["ATX 3.0 power supply", "80 Plus Gold PSU"],
    "Case": ["ATX PC case", "Mini ITX PC case"],
    "Cooler": ["CPU air cooler", "AIO liquid CPU cooler"],
    "Storage": ["NVMe SSD", "PCIe 4.0 SSD"],
    "Monitor": ["gaming monitor", "4K monitor", "OLED gaming monitor"],
    "Keyboard": ["mechanical gaming keyboard"],
    "Mouse": ["wireless gaming mouse"],
    "Headset": ["gaming headset"],
    "Capture Card": ["HDMI capture card"],
    "Fans": ["120mm PWM case fan", "140mm PWM case fan"],
    "Custom Cooling": ["PC water cooling radiator", "CPU water block"],
    "Accessories": ["PC cable extension kit", "GPU support bracket"],
}


def normalize_category(value: str | None) -> str:
    if not value:
        return "Accessories"
    cleaned = re.sub(r"[^a-z0-9+]+", " ", value.lower()).strip()
    if cleaned in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[cleaned]
    for category in GLOBAL_HARDWARE_CATEGORIES:
        if cleaned == category.lower():
            return category
    return "Accessories"


def classify_category(title: str, fallback: str | None = None, specs: dict[str, Any] | None = None) -> str:
    specs = specs or {}
    if specs.get("category"):
        return normalize_category(str(specs["category"]))
    text = f" {title.lower()} "
    for pattern, category in CATEGORY_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return category
    return normalize_category(fallback)


def discovery_queries(categories: list[str] | None = None, query: str | None = None) -> list[tuple[str, str]]:
    normalized = [normalize_category(category) for category in categories or GLOBAL_HARDWARE_CATEGORIES]
    pairs: list[tuple[str, str]] = []
    for category in normalized:
        if query:
            pairs.append((category, f"{query} {category}".strip()))
            continue
        for template in DISCOVERY_QUERY_TEMPLATES.get(category, [category]):
            pairs.append((category, template))
    seen: set[tuple[str, str]] = set()
    unique: list[tuple[str, str]] = []
    for pair in pairs:
        key = (pair[0], pair[1].lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(pair)
    return unique
