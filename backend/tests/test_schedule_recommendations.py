from app.schedule_recommendations import best_schedules


def talk(talk_id: str, start: str, end: str, relevance: float) -> dict[str, object]:
    return {
        "talk_id": talk_id,
        "start_time": start,
        "end_time": end,
        "relevance": relevance,
    }


def test_best_schedules_maximizes_total_relevance_not_greedy_first_choice() -> None:
    talks = [
        talk("long", "2026-11-09T09:00:00Z", "2026-11-09T11:00:00Z", 9),
        talk("morning", "2026-11-09T09:00:00Z", "2026-11-09T10:00:00Z", 5),
        talk("late-morning", "2026-11-09T10:00:00Z", "2026-11-09T11:00:00Z", 5),
        talk("lunch", "2026-11-09T11:00:00Z", "2026-11-09T12:00:00Z", 2),
    ]

    schedules = best_schedules(talks)

    assert schedules[0]["relevance"] == 12
    assert [talk["talk_id"] for talk in schedules[0]["talks"]] == [
        "morning",
        "late-morning",
        "lunch",
    ]


def test_best_schedules_returns_distinct_ranked_options() -> None:
    talks = [
        talk("a", "2026-11-09T09:00:00Z", "2026-11-09T10:00:00Z", 4),
        talk("b", "2026-11-09T09:00:00Z", "2026-11-09T10:00:00Z", 3),
        talk("c", "2026-11-09T10:00:00Z", "2026-11-09T11:00:00Z", 4),
    ]

    schedules = best_schedules(talks, count=2)

    assert [schedule["relevance"] for schedule in schedules] == [8, 7]
    assert [talk["talk_id"] for talk in schedules[1]["talks"]] == ["b", "c"]
