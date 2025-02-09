import os
import xml.etree.ElementTree as ET
import re
import traceback

# local imports
import bme_parser


# Main Process XML data.
def xml_parse(file_path, logger):
    file_name = os.path.splitext(os.path.basename(file_path))[0]
    logger.info(f"Spuštění nové úlohy")
    logger.info(f"Zpracovávání souboru: {file_name}")
    # Get encoding
    encoding = get_encoding_prolog(file_path, logger)
    logger.debug(f"Znaková sada XML souboru: {encoding}")
    # Check doctype and bmecat tags
    if check_bmecat_and_doctype(file_path, logger, encoding):
        try:
            # Get ElementTree root
            ET_root = get_xml_root(file_path, logger)
            if ET_root is None:
                logger.error("xml_parse XML ET_root is none, return.")
                return
            #logger.info(f"Zpracovávání dat")
            bme_parser.parse_BME_header(ET_root, file_name, logger)
            #bme_parser.parse_BME_products(ET_root, file_name, logger)
            #bme_parser.parse_BME_mime(ET_root, file_name, logger)
            #bme_parser.parse_BME_features(ET_root, file_name, logger)
        except Exception as e:
            logger.error(f"Chyba funkce xml_parse: {e}")  
            logger.error(traceback.format_exc())
    else:
        logger.warning(f"Pokus jako obecný xml soubor")
        ET_root = get_xml_root(file_path, logger)
        #raw_json = generic_xml_json(ET_root)
        #save_products(raw_json, file_name)

# Check if the specified file has an XML prolog.
def get_encoding_prolog(file_path, logger):
    ENCODINGS_TO_TRY = ['utf-8', 'utf-16', 'windows-1252', 'latin-1']
    for encoding in ENCODINGS_TO_TRY:
        try:
            logger.info(f"Soubor zkouším otevřít pomocí kódování: {encoding}")
            with open(file_path, 'r', encoding=encoding) as file:
                content = file.read(1024).strip()  # Read first 1024 characters
                # Regular expression to match XML prolog with encoding attribute
                prolog_pattern = r'<\?xml\s+version=["\']1\.[0-9]["\']\s*(encoding=["\']([^"\']+)["\'])?\s*(standalone=["\'](yes|no)["\'])?\s*\?>'
                prolog_match = re.search(prolog_pattern, content)
                if prolog_match:
                    prolog = prolog_match.group(0).strip()
                    declared_encoding = prolog_match.group(2)  # Capture the encoding if present
                    standalone = prolog_match.group(4)  # Capture the standalone attribute if present
                    logger.info(f"XML prolog je validní, znaková sada prologu je: {declared_encoding}")
                    logger.debug(f"XML prolog: {prolog}")
                    if standalone:
                        logger.debug(f"Standalone atribut v prologu: {standalone}")
                    if declared_encoding is None:
                        logger.warning(f"Prolog znakové sada nenalezen. Výchozí znaková sada: {encoding}")
                        return encoding
                    return declared_encoding
                else:
                    logger.error(f"Nenalezen XML prolog. Nastavena znaková sada: {encoding}")
                    return encoding
        except Exception as e:
            logger.error(f"Chyba funkce check_xml_prolog: {e}")

# Check DOCTYPE & BMECAT tags
def check_bmecat_and_doctype(file_path, logger, encoding='utf-8'):
    # Helper Extract tag for check DOCTYPE & BMECAT
    def extract_tag(content, tag_name, logger):
        tag_start = content.find(tag_name)
        if tag_start != -1:
            tag_end = content.find('>', tag_start) + 1  # Include the closing '>'
            tag_content = content[tag_start:tag_end]
            logger.debug(f"{tag_name} nalezen: {tag_content}")
            return tag_content
        logger.info(f"Nenalezen {tag_name}")
      
    try:
        with open(file_path, 'r', encoding=encoding) as file:
            # Read the first 512 characters
            content = file.read(512)
            doctype_content = extract_tag(content, '<!DOCTYPE', logger)
            BMECAT_content = extract_tag(content, '<BMECAT', logger)
            if BMECAT_content is not None:
                if "version=\"2005\"" in BMECAT_content:
                    logger.info("BMEcatalog verze: 2005")
                return True
            else:
                logger.error("Soubor není v ETIM formátu")
                return False
    except Exception as e:
        logger.error(f"Chyba funkce validate_BMEcat: {e}")
        return False

# Validate XML
def get_xml_root(file_path, logger):
    try:
        # Parse the XML file
        tree = ET.parse(file_path)
        root = tree.getroot()
        logger.info("XML soubor je validní.")
        # Check if there is a namespace        
        if '}' in root.tag:
            namespace = root.tag.split('}')[0].strip('{')  # Get the namespace URI
            logger.info(f"Namespace: {namespace}")
        else:
            namespace = None
            logger.info("Namespace nenalezen.")
        # Strip namespace
        for elem in root.iter():
            elem.tag = elem.tag.split("}")[-1]  # Strip namespace from each tag
        return root
    except ET.ParseError as e:
        logger.error(f"Chyba v XML souboru: {e}")
        return None
    except Exception as e:
        logger.error(f"Chyba funkce validate_xml: {e}")
        return None