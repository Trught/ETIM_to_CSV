import sys
import signal
import os
import logging


# local imports
import xml_utils

def handle_keyboard_interrupt(signum, frame):
    logging.info("Přijat Ctrl+C KeyboardInterrupt. Přerušuji.")
    raise SystemExit

def setup_signal_handler():
    signal.signal(signal.SIGINT, handle_keyboard_interrupt)

# Set up logging to both console and a file.
def setup_logging(log_file='BME_parse.log', log_level=logging.DEBUG):
    # Create a logger
    logger = logging.getLogger()
    # Set the logging level
    logger.setLevel(log_level)  # Set the logging level for the logger
    # Create a file handler with UTF-8 encoding
    file_handler_output = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    file_handler_output.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    # Create a stream handler to output to console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    # Add the handlers to the logger
    logger.addHandler(file_handler_output)
    logger.addHandler(console_handler)
    return logger

# Print help
def print_help():
    help_message = """
    Použití: python BME_parse.py <XML_soubor>
    
    Argumenty:
        <BMEcat_XML_soubor> : Cesta k BMEcat(ETIM) XML souboru.
    
    Pokud není zadán žádný argument nebo pokud zadaný argument není platný soubor XML, zobrazí se tato nápověda.
    Zpracování lze přerušit zkratkou 'Ctrl + C'
    """
    print(help_message)

# Main & arg check
def main():
    # Check if debug flag is present
    debug_mode = "-debug" in sys.argv
    # Remove debug argument if present
    args = [arg for arg in sys.argv[1:] if arg != "-debug"]
    
    # Check if a file argument is provided
    if len(args) > 0:
        droppedFile = args[0]
        # Check if the provided file exists
        if os.path.exists(droppedFile):
            # Ensure the output directory exists
            os.makedirs('output', exist_ok=True)
            xml_file = droppedFile
            file_name = os.path.splitext(os.path.basename(xml_file))[0]
            log_level = logging.DEBUG if debug_mode else logging.INFO
            logger = setup_logging(log_file = "output/" + file_name + "_log.txt", log_level=log_level)
            
            # Process the XML file
            xml_utils.xml_parse(xml_file, logger)
            
        else:
            logger = setup_logging(log_file = "error_log.txt")
            logger.error(f"Soubor '{droppedFile}' neexistuje.")
            print_help()
            return
        
    else:
        print_help()

if __name__ == "__main__":
    setup_signal_handler()
    main()
