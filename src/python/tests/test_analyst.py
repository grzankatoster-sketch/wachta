from wachta_detectors.analyst import (
    Analyst,
    Fact,
    build_prompt,
    judge,
    numbers_in,
    review,
    split_sentences,
)
from wachta_detectors.embeddings import DeterministicEmbedder
from wachta_detectors.vector_store import Document, InMemoryVectorStore, index_documents

FAKTY = [
    Fact(1, "Wsparcie dla Ukrainy przekazane lacznie: 426 mld dolarow, w tym wojskowe 205 mld."),
    Fact(2, "Detektor D4 na dobie dunskiego AIS znalazl 4 niewyjasnione ciszy."),
    Fact(3, "Statek STANISLAV GOVORUKHIN milczal 46 minut i pojawil sie 16.3 km dalej."),
]


def test_sentence_without_a_reference_is_dropped():
    v = judge("Sytuacja jest napieta i wymaga uwagi.", FAKTY)
    assert not v.accepted and "brak odnosnika" in v.reason


def test_reference_to_a_fact_that_does_not_exist_is_dropped():
    v = judge("Cos sie wydarzylo [9].", FAKTY)
    assert not v.accepted and "nieistniejacego" in v.reason


def test_faithful_sentence_passes():
    assert judge("Wsparcie wyniosло 426 mld dolarow [1].".replace("о", "o"), FAKTY).accepted


def test_number_absent_from_the_cited_fact_is_dropped():
    # To jest ta dziura, ktora pierwsza wersja bramki przepuszczala: odnosnik prawdziwy, liczba nie.
    v = judge("Wsparcie wyniosло 999 mld dolarow [1].".replace("о", "o"), FAKTY)
    assert not v.accepted and "spoza cytowanych faktow" in v.reason


def test_number_taken_from_another_cited_fact_is_fine():
    assert judge("Znaleziono 4 ciszy, w tym jedna trwajaca 46 minut [2][3].", FAKTY).accepted


def test_number_from_an_uncited_fact_is_not_enough():
    assert not judge("Znaleziono 46 przypadkow [2].", FAKTY).accepted


def test_reference_number_itself_is_not_treated_as_a_claim():
    # Bez tego "[3]" uzasadnialby sam siebie i kazde zdanie z odnosnikiem [3] przechodziloby liczbowo.
    assert judge("Statek milczal 46 minut [3].", FAKTY).accepted
    assert not judge("Statek milczal 47 minut [3].", FAKTY).accepted


def test_decimal_comma_and_dot_are_the_same_number():
    assert judge("Pojawil sie 16,3 km dalej [3].", FAKTY).accepted


def test_sentence_with_no_numbers_only_needs_a_reference():
    assert judge("Detektor wskazal kilka przypadkow do sprawdzenia [2].", FAKTY).accepted


def test_review_separates_the_two_piles_and_counts_them():
    nota = ("Wsparcie wyniosло 426 mld dolarow [1]. "
            "Przyczyny tych zdarzen pozostaja nieznane. "
            "Detektor znalazl 4 ciszy [2].").replace("о", "o")
    przyjete, odrzucone = review(nota, FAKTY)
    assert len(przyjete) == 2
    assert len(odrzucone) == 1
    assert "brak odnosnika" in odrzucone[0].reason


def test_numbers_in_folds_the_comma_and_trailing_zeros():
    assert numbers_in("16,3 km i 46 minut") == {"16.3", "46"}
    assert numbers_in("9,0 m") == numbers_in("9 m")


def test_split_sentences_handles_an_empty_note():
    assert split_sentences("") == []
    assert split_sentences(None) == []


def test_prompt_contains_every_fact_numbered():
    prompt = build_prompt("ile dano Ukrainie?", FAKTY)
    for f in FAKTY:
        assert f"[{f.number}]" in prompt
    assert "ile dano Ukrainie?" in prompt


def sklep() -> InMemoryVectorStore:
    store = InMemoryVectorStore()
    index_documents(store, DeterministicEmbedder(), [
        Document("a", "tankowiec zgasil transponder przy kablu podmorskim"),
        Document("b", "prognoza pogody na weekend w gorach"),
    ])
    return store


def test_analyst_publishes_only_what_survives_the_gates():
    analyst = Analyst(sklep(), DeterministicEmbedder(),
                      ask_model=lambda p: "Tankowiec zgasil transponder [1]. Zrobil to celowo.")
    answer = analyst.answer("tankowiec zgasil transponder przy kablu podmorskim")
    assert answer.accepted == ["Tankowiec zgasil transponder [1]."]
    assert len(answer.rejected) == 1
    assert 0 < answer.kept_share < 1


def test_analyst_does_not_ask_the_model_when_nothing_is_relevant():
    pytano = []

    def model(prompt):
        pytano.append(prompt)
        return "cokolwiek [1]."

    analyst = Analyst(sklep(), DeterministicEmbedder(), ask_model=model, min_score=0.99)
    answer = analyst.answer("zupelnie inny temat")
    assert answer.facts == []
    assert answer.accepted == []
    assert pytano == [], "brak faktow to odpowiedz, a nie powod do pytania modelu"


def test_analyst_hands_the_model_the_retrieved_facts():
    widziane = {}

    def model(prompt):
        widziane["prompt"] = prompt
        return "Tankowiec zgasil transponder [1]."

    Analyst(sklep(), DeterministicEmbedder(), ask_model=model).answer(
        "tankowiec zgasil transponder przy kablu podmorskim")
    assert "transponder" in widziane["prompt"]


def test_a_range_of_references_is_a_reference():
    # Znalezione na zywym przebiegu: model napisal uczciwe "brak danych w podanych faktach [1-3]",
    # a bramka odrzucila to jako zdanie bez odnosnika.
    v = judge("Brak danych o tej sprawie w podanych faktach [1-3].", FAKTY)
    assert v.accepted, v.reason


def test_a_list_of_references_also_counts():
    assert judge("Oba detektory cos wskazaly [2,3].", FAKTY).accepted


def test_a_range_reaching_past_the_facts_is_still_refused():
    v = judge("Wszystko to wynika z faktow [1-9].", FAKTY)
    assert not v.accepted and "nieistniejacego" in v.reason


def test_numbers_are_still_checked_inside_a_range():
    assert not judge("Znaleziono 999 przypadkow [1-3].", FAKTY).accepted


def test_a_reference_with_no_sentence_is_not_a_sentence():
    # Model zapytany o Iran odpowiedzial miedzy innymi samym "[8]".
    v = judge("[8]", FAKTY)
    assert not v.accepted and "bez tresci" in v.reason


def test_two_words_plus_a_reference_is_still_too_little():
    assert not judge("Brak danych [1].", FAKTY).accepted


def test_the_same_sentence_repeated_counts_once():
    """Znalezione na zywym przebiegu: model powtorzyl jedno zdanie osiem razy, zmieniajac tylko
    numer odnosnika. Wszystkie mialy poprawne odnosniki i zadnych liczb, wiec bramka przyjela
    osiem z dziewieciu zdan i ogłosila 89% przyjetych - liczbe zupelnie bez znaczenia."""
    nota = " ".join(f"Brak danych o sytuacji w tym kraju [{i}]." for i in range(1, 4))
    przyjete, odrzucone = review(nota, FAKTY)
    assert len(przyjete) == 1
    assert len(odrzucone) == 2
    assert all("powtorzenie" in j.reason for j in odrzucone)


def test_different_sentences_citing_the_same_fact_both_stay():
    nota = "Statek milczal 46 minut [3]. Pojawil sie 16,3 km dalej [3]."
    przyjete, odrzucone = review(nota, FAKTY)
    assert len(przyjete) == 2 and odrzucone == []
