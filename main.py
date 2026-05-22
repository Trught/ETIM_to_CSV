import sys
import signal
import os
import logging
import argparse

# Zabrání vytváření .pyc pro aktuální proces
sys.dont_write_bytecode = True

# local imports
import xml_utils


def handle_signal(signum, frame):
    raise SystemExit(128 + signum)


def setup_signal_handler():
    signal.signal(signal.SIGINT, handle_signal)  # Ctrl+C
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_signal)


# Set up logging to both console and a file.
def setup_logging(log_file: str, log_level: int = logging.INFO) -> logging.Logger:
    # Create a logger
    logger = logging.getLogger("bme_parser")
    # Set the logging level
    logger.setLevel(log_level)  # Set the logging level for the logger
    logger.propagate = False
    
    # Clear handlers
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    # Create a file handler with UTF-8 encoding
    file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    file_handler.setFormatter(formatter)
    # Create a stream handler to output to console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    # Add the handlers to the logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger



def create_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="BME-tool",
        description=(
            "Zpracuje BMEcat(ETIM) XML soubor streamově, "
            "bez načtení celého rootu do RAM."
        ),
        add_help=False
    )

    parser.add_argument(
        "xml_file",
        nargs="?",
        help="Cesta k BMEcat(ETIM) XML souboru."
    )

    parser.add_argument(
        "-debug",
        action="store_true",
        help="Zapne detailní logování."
    )
    
    parser.add_argument(
        "-h",
        "--help",
        action="help",
        help="Zobrazí tuto nápovědu a ukončí program."
    )

    return parser

def pause_on_windows():
    if os.name == "nt":
        print("Stiskněte libovolnou klávesu pro ukončení . . .")
        os.system("pause >nul")

# Main & arg check
def main():
    parser = create_arg_parser()
    args = parser.parse_args()

    if not args.xml_file:
        parser.print_help()
        pause_on_windows()
        return 1

    dropped_file = args.xml_file
    debug_mode = args.debug


    if not os.path.isfile(dropped_file):
        logger = setup_logging(log_file="error_log.txt")
        logger.error("Soubor '%s' neexistuje nebo není soubor.", dropped_file)
        parser.print_help()
        return 1

    if not dropped_file.lower().endswith(".xml"):
        logger = setup_logging(log_file="error_log.txt")
        logger.error("Soubor '%s' není XML soubor.", dropped_file)
        parser.print_help()
        return 1

    # Ensure the output directory exists
    os.makedirs("output", exist_ok=True)

    file_name = os.path.splitext(os.path.basename(dropped_file))[0]
    log_file = os.path.join("output", f"{file_name}_log.txt")
    log_level = logging.DEBUG if debug_mode else logging.INFO
    logger = setup_logging(log_file=log_file, log_level=log_level)

    try:
        logger.info("Spouštím zpracování souboru: %s", dropped_file)
        xml_utils.xml_parse(dropped_file, logger)
        logger.info("Zpracování dokončeno.")
        return 0

    except KeyboardInterrupt:
        logger.warning("Zpracování přerušeno uživatelem.")
        return 130

    except SystemExit as exc:
        logger.warning("Aplikace ukončena signálem.")
        return exc.code if isinstance(exc.code, int) else 1

    except Exception:
        logger.exception("Při zpracování XML došlo k neočekávané chybě.")
        return 1


if __name__ == "__main__":
    setup_signal_handler()
    sys.exit(main())
