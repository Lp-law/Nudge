EN_TO_HE_MAP = {
    "q": "/",
    "w": "'",
    "e": "ק",
    "r": "ר",
    "t": "א",
    "y": "ט",
    "u": "ו",
    "i": "ן",
    "o": "ם",
    "p": "פ",
    "[": "]",
    "]": "[",
    "\\": "\\",
    "a": "ש",
    "s": "ד",
    "d": "ג",
    "f": "כ",
    "g": "ע",
    "h": "י",
    "j": "ח",
    "k": "ל",
    "l": "ך",
    ";": "ף",
    "'": ",",
    "z": "ז",
    "x": "ס",
    "c": "ב",
    "v": "ה",
    "b": "נ",
    "n": "מ",
    "m": "צ",
    ",": "ת",
    ".": "ץ",
    "/": ".",
}


def convert_en_layout_to_hebrew(text: str) -> str:
    output: list[str] = []
    for char in text:
        mapped = EN_TO_HE_MAP.get(char.lower())
        output.append(mapped if mapped is not None else char)
    return "".join(output)
