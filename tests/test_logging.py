import logging

import main


def test_configure_logging_appends_file_without_replacing_console_handlers(
    monkeypatch, tmp_path
):
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level
    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("LOG_LEVEL", "INFO")

    try:
        main.configure_logging()
        console_handlers = [
            handler
            for handler in root_logger.handlers
            if not getattr(handler, "_ipo_radar_file_handler", False)
        ]
        file_handlers = [
            handler
            for handler in root_logger.handlers
            if getattr(handler, "_ipo_radar_file_handler", False)
        ]
        assert len(file_handlers) == 1
        assert file_handlers[0].mode == "a"
        assert (tmp_path / "logs").is_dir()

        def emit(message):
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname=__file__,
                lineno=1,
                msg=message,
                args=(),
                exc_info=None,
            )
            file_handlers[0].emit(record)

        emit("first run")
        file_handlers[0].flush()

        main.configure_logging()
        assert [
            handler
            for handler in root_logger.handlers
            if getattr(handler, "_ipo_radar_file_handler", False)
        ] == file_handlers
        assert [
            handler
            for handler in root_logger.handlers
            if not getattr(handler, "_ipo_radar_file_handler", False)
        ] == console_handlers

        root_logger.removeHandler(file_handlers[0])
        file_handlers[0].close()
        main.configure_logging()
        file_handlers = [
            handler
            for handler in root_logger.handlers
            if getattr(handler, "_ipo_radar_file_handler", False)
        ]
        assert len(file_handlers) == 1
        emit("second run")
        file_handlers[0].flush()

        log_path = tmp_path / "logs" / "ipo_radar.log"
        log_text = log_path.read_text(encoding="utf-8")
        assert " INFO first run\n" in log_text
        assert " INFO second run\n" in log_text
    finally:
        for handler in list(root_logger.handlers):
            if handler not in original_handlers:
                root_logger.removeHandler(handler)
                handler.close()
        root_logger.setLevel(original_level)
