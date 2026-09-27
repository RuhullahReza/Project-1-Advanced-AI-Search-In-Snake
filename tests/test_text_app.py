from snake_game.text_app import main


def test_text_mode_describes_board_and_accepts_human_move(monkeypatch, capsys):
    commands = iter(["board", "up", "restart", "quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(commands))
    main(["--mode", "versus", "--rows", "10", "--columns", "10"])
    output = capsys.readouterr().out
    assert "body, head to tail" in output
    assert "direction up" in output
    assert "Apples:" in output


def test_text_mode_ai_decision(monkeypatch, capsys):
    commands = iter(["next", "quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(commands))
    main([])
    assert "Round 1 of 200" in capsys.readouterr().out


def test_text_mode_ai_vs_ai_advances_both_strategies(monkeypatch, capsys):
    commands = iter(["next", "next", "quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(commands))
    main(["--mode", "ai-vs-ai", "--rows", "10", "--columns", "10"])
    output = capsys.readouterr().out
    assert "AI 1 thinking." in output
    assert "AI 2 thinking." in output
    assert "Round 1 of 200" in output
