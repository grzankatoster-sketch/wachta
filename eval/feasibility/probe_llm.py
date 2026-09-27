"""Measures local qwen extraction of war-event facts to JSON, plus bge-m3 cross-lingual similarity."""
import json, time, sys, math
import requests

sys.stdout.reconfigure(encoding="utf-8")
O = "http://localhost:11434"
ART = {
    "uk": "Вночі російські війська завдали ракетного удару по Одесі. Пошкоджено житловий будинок, загинули 4 цивільних, ще 11 поранено. Про це повідомив голова ОВА Олег Кіпер.",
    "ru": "Ночью ВС РФ нанесли высокоточный удар по объектам военной инфраструктуры в Одессе. Уничтожен склад боеприпасов ВСУ, сообщает Минобороны России.",
    "en": "A missile strike hit Odesa overnight. Ukrainian officials say four civilians were killed; Russia claims it targeted an ammunition depot. The claims could not be independently verified.",
}
SCHEMA = {"type": "object", "properties": {
    "location": {"type": "string"}, "time": {"type": "string"}, "actor": {"type": "string"}, "event_type": {"type": "string"},
    "target_claimed": {"type": "string"}, "civilian_deaths": {"type": ["integer", "null"]}, "source_cited": {"type": "string"}},
    "required": ["location", "actor", "event_type", "target_claimed", "civilian_deaths", "source_cited"]}

for lang, txt in ART.items():
    t = time.time()
    r = requests.post(f"{O}/api/chat", json={"model": "qwen3.5:9b", "stream": False, "think": False, "format": SCHEMA,
        "options": {"temperature": 0, "num_ctx": 2048}, "keep_alive": "2m",
        "messages": [{"role": "user", "content": "Extract facts from this news text into JSON, values in English. Use null if not stated.\n\n" + txt}]}, timeout=600).json()
    print(lang, f"{time.time()-t:.1f}s", r["message"]["content"])

def emb(texts):
    return requests.post(f"{O}/api/embed", json={"model": "bge-m3", "input": texts, "keep_alive": "1m"}, timeout=300).json()["embeddings"]

def cos(a, b):
    return sum(x*y for x, y in zip(a, b)) / (math.sqrt(sum(x*x for x in a)) * math.sqrt(sum(y*y for y in b)))

other = "Na Bałtyku zakończyły się ćwiczenia marynarki wojennej NATO, w których wzięło udział 30 okrętów."
t = time.time(); E = emb(list(ART.values()) + [other]); print(f"\nembeddingi 4 tekstow: {time.time()-t:.1f}s")
print("podobienstwo UA-RU (to samo zdarzenie):", round(cos(E[0], E[1]), 3))
print("podobienstwo UA-EN (to samo zdarzenie):", round(cos(E[0], E[2]), 3))
print("podobienstwo UA-PL (inne zdarzenie):   ", round(cos(E[0], E[3]), 3))
print(requests.get(f"{O}/api/ps").json())
