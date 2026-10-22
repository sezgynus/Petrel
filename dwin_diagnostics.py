"""Load full exception diagnostics only when the broker actually needs them."""


def log_exception(logger_name, message, *args):
    # Stay inside the caller's exception context so traceback details survive.
    import logging
    logging.basicConfig(level=logging.INFO)
    logging.getLogger(logger_name).exception(message, *args)
