import sys
import signal
import os
import logging


# local imports
import xml_utils
#import bme_parser

def handle_keyboard_interrupt(signum, frame):
    logging.info("Přijat Ctrl+C KeyboardInterrupt. Přerušuji.")
    raise SystemExit

def setup_signal_handler():
    signal.signal(signal.SIGINT, handle_keyboard_interrupt)

# Set up logging to both console and a file.
def setup_logging(log_file='BME_parse.log', log_level=logging.INFO):
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
    """
    print(help_message)

# Main & arg check
def main():
    # Check if a file argument is provided
    if len(sys.argv) > 1:
        droppedFile = sys.argv[1]
        # Check if the provided file exists
        if os.path.exists(droppedFile):
            # Ensure the output directory exists
            os.makedirs('output', exist_ok=True)
            xml_file = droppedFile
            file_name = os.path.splitext(os.path.basename(xml_file))[0]
            logger = setup_logging(log_file = "output/" + file_name + "_log.txt")
            
            # Process the XML file
            xml_utils.xml_parse(xml_file, logger)
            
        else:
            logger = setup_logging(log_file = "error_log.txt")
            logger.error(f"Soubor '{droppedFile}' neexistuje.")
            print_help()
            return
        
    else:
        print_help()
        logger.warning(f"Nebyl poskytnut žádný argument.")

if __name__ == "__main__":
    setup_signal_handler()
    main()