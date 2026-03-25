"""Multilingual message bundle for transliterated Farsi/Persian greetings.

This module captures one concrete message pattern across:
- Persian in Latin transliteration
- Persian in native script
- English gloss
- French translation

It also exposes a compact JSON-LD style context, a graph-oriented view, and a
small training dataset suitable for integration tests and fixture generation.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


BASE_MESSAGE_LATIN = (
    "salam ostaad. goftam salami karde baasham va inke etminan haasel konam "
    "ke shoma va khaanevaadeye aziz hame sahih va salaamatid ❤️"
)

BASE_MESSAGE_PERSIAN = (
    "سلام استاد. گفتم سلامی کرده باشم و این‌که اطمینان حاصل کنم که شما و "
    "خانوادهٔ عزیز همه صحیح و سلامتید ❤️"
)

BASE_MESSAGE_ENGLISH = (
    "Hello professor. I wanted to say hello and make sure that you and your "
    "dear family are all well and safe. ❤️"
)

BASE_MESSAGE_FRENCH = (
    "Bonjour professeur. Je voulais vous saluer et m'assurer que vous et votre "
    "chère famille allez bien et êtes en sécurité. ❤️"
)


@dataclass(frozen=True)
class MultilingualMessageExample:
    """A single training example spanning transliteration and translations."""

    example_id: str
    source_text_latin: str
    source_text_persian: str
    english_translation: str
    french_translation: str
    language_path: List[str]
    register: str
    speech_acts: List[str]
    emotions: List[str]
    intents: List[str]
    recipient_relation: str
    script_type: str = "transliteration"
    causality_guard: Dict[str, Any] = field(default_factory=dict)
    context_dimensions: Dict[str, Any] = field(default_factory=dict)


def knowledge_graph_context() -> Dict[str, Any]:
    """Return a JSON-LD style context for multilingual emotional messages."""
    return {
        "@context": {
            "id": "@id",
            "type": "@type",
            "label": "http://www.w3.org/2000/01/rdf-schema#label",
            "message": "https://singine.local/ontology/message#",
            "Message": "https://singine.local/ontology/message#Message",
            "Person": "https://schema.org/Person",
            "Emotion": "https://singine.local/ontology/affect#Emotion",
            "Intent": "https://singine.local/ontology/intent#Intent",
            "SpeechAct": "https://singine.local/ontology/speech#SpeechAct",
            "Dataset": "https://www.w3.org/ns/dcat#Dataset",
            "InfoSet": "https://singine.local/ontology/data#InfoSet",
            "ActivitySet": "https://singine.local/ontology/activity#ActivitySet",
            "textFaLatn": "https://singine.local/ontology/lang#textFaLatn",
            "textFa": "https://singine.local/ontology/lang#textFa",
            "textEn": "https://singine.local/ontology/lang#textEn",
            "textFr": "https://singine.local/ontology/lang#textFr",
            "register": "https://singine.local/ontology/social#register",
            "emotion": {"@id": "https://singine.local/ontology/affect#emotion", "@type": "@id"},
            "intent": {"@id": "https://singine.local/ontology/intent#intent", "@type": "@id"},
            "speechAct": {"@id": "https://singine.local/ontology/speech#speechAct", "@type": "@id"},
            "sender": {"@id": "https://schema.org/sender", "@type": "@id"},
            "recipient": {"@id": "https://schema.org/recipient", "@type": "@id"},
            "familyReference": "https://singine.local/ontology/social#familyReference",
            "temporalRelation": "https://singine.local/ontology/time#temporalRelation",
            "causalityGuard": "https://singine.local/ontology/time#causalityGuard",
            "preservationPolicy": "https://singine.local/ontology/time#preservationPolicy",
            "outerDimension": "https://singine.local/ontology/context#outerDimension",
            "innerDimension": "https://singine.local/ontology/context#innerDimension",
            "geometry": "https://singine.local/ontology/geometry#geometry",
            "gaugeAlignment": "https://singine.local/ontology/geometry#gaugeAlignment",
            "cycleSpace": "https://singine.local/ontology/geometry#cycleSpace",
            "dataPlatform": "https://singine.local/ontology/platform#dataPlatform",
            "sqlBackend": "https://singine.local/ontology/platform#sqlBackend",
            "edgeRuntime": "https://singine.local/ontology/platform#edgeRuntime",
        }
    }


def message_graph() -> Dict[str, Any]:
    """Return a graph-shaped bundle for the seed greeting and its context."""
    return {
        **knowledge_graph_context(),
        "id": "urn:singine:message:fa-latn:greeting-001",
        "type": "Message",
        "label": "Farsi transliterated wellbeing greeting",
        "textFaLatn": BASE_MESSAGE_LATIN,
        "textFa": BASE_MESSAGE_PERSIAN,
        "textEn": BASE_MESSAGE_ENGLISH,
        "textFr": BASE_MESSAGE_FRENCH,
        "register": "polite_affectionate",
        "sender": "urn:singine:person:student-or-junior",
        "recipient": "urn:singine:person:elder-or-teacher",
        "familyReference": True,
        "speechAct": [
            "urn:singine:speech:greeting",
            "urn:singine:speech:wellbeing-check",
            "urn:singine:speech:relationship-maintenance",
        ],
        "emotion": [
            "urn:singine:emotion:care",
            "urn:singine:emotion:respect",
            "urn:singine:emotion:benevolence",
            "urn:singine:emotion:warmth",
        ],
        "intent": [
            "urn:singine:intent:say-hello",
            "urn:singine:intent:confirm-safety",
            "urn:singine:intent:preserve-relationship",
        ],
        "temporalRelation": {
            "mode": "present-concern",
            "sequence": ["greeting", "safety-check", "affective-closure"],
        },
        "causalityGuard": {
            "preserve_event_order": True,
            "do_not_infer_harm_from_checking": True,
            "allow_concern_without_damage_claim": True,
        },
        "preservationPolicy": {
            "retain_source_transliteration": True,
            "retain_persian_script_normalization": True,
            "retain_parallel_english_and_french_forms": True,
        },
        "outerDimension": {
            "infrastructure": ["docker", "edge-servers"],
            "data_platforms": ["hive", "datasets", "infosets"],
            "sql_standardization": "hive-sql",
        },
        "innerDimension": {
            "social_hierarchy": "respectful-address",
            "latent_affect": ["care", "tenderness", "light-concern"],
            "memory_pressure": "relationship-maintenance",
        },
        "geometry": {
            "shape_family": ["cycle", "node-edge", "concentric-shells"],
            "cycleSpace": "S1",
            "gaugeAlignment": ["local-state-preservation", "symmetry-aware-labeling"],
            "unity_driver": "single-message-many-representations",
        },
        "dataPlatform": {
            "dataset": "urn:singine:dataset:multilingual-emotion",
            "infoset": "urn:singine:infoset:farsi-english-french-greetings",
            "activitySet": "urn:singine:activityset:care-messages",
        },
        "sqlBackend": {
            "engine": "Hive",
            "table_family": ["messages", "message_annotations", "message_relations"],
        },
        "edgeRuntime": {
            "containerization": "Docker",
            "distribution": "edge-synchronized",
        },
    }


def _base_dimensions() -> Dict[str, Any]:
    return {
        "inner": {
            "social_hierarchy": "respectful-address",
            "affect_trace": ["care", "respect", "benevolence"],
        },
        "outer": {
            "languages": ["fa-Latn", "fa", "en", "fr"],
            "systems": ["knowledge-graph", "dataset", "infoset", "activity-set"],
        },
    }


def training_examples() -> List[MultilingualMessageExample]:
    """Return a compact multilingual dataset for test and fixture generation."""
    shared_guard = {
        "preserve_event_order": True,
        "do_not_infer_harm_from_checking": True,
        "preserve_parallel_texts": True,
    }
    examples = [
        MultilingualMessageExample(
            example_id="ME001",
            source_text_latin=BASE_MESSAGE_LATIN,
            source_text_persian=BASE_MESSAGE_PERSIAN,
            english_translation=BASE_MESSAGE_ENGLISH,
            french_translation=BASE_MESSAGE_FRENCH,
            language_path=["fa-Latn", "fa", "en", "fr"],
            register="polite_affectionate",
            speech_acts=["greeting", "wellbeing_check", "relationship_maintenance"],
            emotions=["care", "respect", "benevolence", "warmth"],
            intents=["say_hello", "confirm_safety", "preserve_relationship"],
            recipient_relation="elder_or_teacher",
            causality_guard=shared_guard,
            context_dimensions=_base_dimensions(),
        ),
        MultilingualMessageExample(
            example_id="ME002",
            source_text_latin="salam ostad. khastam ahvaaletoon ro beporsam va bebinam hamechi rooberaah hast ❤️",
            source_text_persian="سلام استاد. خواستم احوالتون رو بپرسم و ببینم همه‌چی روبه‌راه هست ❤️",
            english_translation="Hello professor. I wanted to ask how you are and see whether everything is going well. ❤️",
            french_translation="Bonjour professeur. Je voulais prendre de vos nouvelles et voir si tout va bien. ❤️",
            language_path=["fa-Latn", "fa", "en", "fr"],
            register="warm_respectful",
            speech_acts=["greeting", "status_check"],
            emotions=["care", "warmth"],
            intents=["check_wellbeing", "maintain_connection"],
            recipient_relation="elder_or_teacher",
            causality_guard=shared_guard,
            context_dimensions=_base_dimensions(),
        ),
        MultilingualMessageExample(
            example_id="ME003",
            source_text_latin="salam. goftam az shoma va khaanevaadeh-ye mehrabaan khabari begiram 🌷",
            source_text_persian="سلام. گفتم از شما و خانوادهٔ مهربان خبری بگیرم 🌷",
            english_translation="Hello. I thought I would check in on you and your kind family. 🌷",
            french_translation="Bonjour. Je me suis dit que j'allais prendre des nouvelles de vous et de votre aimable famille. 🌷",
            language_path=["fa-Latn", "fa", "en", "fr"],
            register="tender_respectful",
            speech_acts=["greeting", "wellbeing_check"],
            emotions=["tenderness", "care"],
            intents=["check_wellbeing", "affirm_affection"],
            recipient_relation="elder_or_teacher",
            causality_guard=shared_guard,
            context_dimensions=_base_dimensions(),
        ),
        MultilingualMessageExample(
            example_id="ME004",
            source_text_latin="salam ostad. omidvaaram shoma va azizan dar salaamati-ye kaamel bashid",
            source_text_persian="سلام استاد. امیدوارم شما و عزیزان در سلامتی کامل باشید",
            english_translation="Hello professor. I hope you and your loved ones are in complete health.",
            french_translation="Bonjour professeur. J'espère que vous et vos proches êtes en parfaite santé.",
            language_path=["fa-Latn", "fa", "en", "fr"],
            register="formal_kind",
            speech_acts=["greeting", "goodwish"],
            emotions=["respect", "benevolence"],
            intents=["wish_health", "maintain_connection"],
            recipient_relation="elder_or_teacher",
            causality_guard=shared_guard,
            context_dimensions=_base_dimensions(),
        ),
        MultilingualMessageExample(
            example_id="ME005",
            source_text_latin="salam. faghat mikhastam etminaan peydaa konam ke hame chi baraye shoma khoob ast",
            source_text_persian="سلام. فقط می‌خواستم اطمینان پیدا کنم که همه‌چیز برای شما خوب است",
            english_translation="Hello. I just wanted to make sure that everything is good for you.",
            french_translation="Bonjour. Je voulais simplement m'assurer que tout va bien pour vous.",
            language_path=["fa-Latn", "fa", "en", "fr"],
            register="gentle_formal",
            speech_acts=["greeting", "reassurance_check"],
            emotions=["concern", "care"],
            intents=["seek_reassurance", "maintain_connection"],
            recipient_relation="respected_person",
            causality_guard=shared_guard,
            context_dimensions=_base_dimensions(),
        ),
        MultilingualMessageExample(
            example_id="ME006",
            source_text_latin="salam ostad. derang shod ama delam khaast ahvaal-e shoma ro bedoonam",
            source_text_persian="سلام استاد. دیرنگ شد اما دلم خواست احوال شما رو بدونم",
            english_translation="Hello professor. It has been a while, but I wanted to know how you are.",
            french_translation="Bonjour professeur. Cela fait un moment, mais je voulais savoir comment vous allez.",
            language_path=["fa-Latn", "fa", "en", "fr"],
            register="respectful_reconnecting",
            speech_acts=["greeting", "reconnection", "status_check"],
            emotions=["care", "regret_light"],
            intents=["reconnect", "check_wellbeing"],
            recipient_relation="elder_or_teacher",
            causality_guard=shared_guard,
            context_dimensions=_base_dimensions(),
        ),
    ]
    return examples


def bundle() -> Dict[str, Any]:
    """Return the full multilingual schema and dataset bundle."""
    return {
        "schema": knowledge_graph_context(),
        "graph": message_graph(),
        "dataset": {
            "id": "urn:singine:dataset:multilingual-emotion",
            "type": "Dataset",
            "label": "Multilingual emotional greeting dataset",
            "languages": ["fa-Latn", "fa", "en", "fr"],
            "examples": [asdict(example) for example in training_examples()],
        },
    }


def scenario_fixture() -> Dict[str, Any]:
    """Return a stable fixture with scenario metadata for the integration layer."""
    payload = bundle()
    fixture = deepcopy(payload)
    fixture["scenario"] = {
        "id": "TC-ME-001",
        "name": "multilingual-emotion-bundle",
        "focus": [
            "knowledge-graph",
            "multilingual-alignment",
            "temporal-causality-protection",
            "geometry-aware-context",
        ],
        "systems": ["S1", "gauge-theory-alignment", "Hive", "Docker", "edge-servers"],
    }
    return fixture
