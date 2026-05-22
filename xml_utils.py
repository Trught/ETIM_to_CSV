import csv
import os
import re
import traceback
import xml.etree.ElementTree as ET

# local imports
import bme_parser


# Main Process XML data.
def xml_parse(file_path, logger, batch_size=100):
    file_name = os.path.splitext(os.path.basename(file_path))[0]
    logger.info(f"Spuštění nové úlohy")
    logger.info(f"Zpracovávání souboru: {file_name}")

    # Get encoding
    encoding = get_xml_declared_encoding(file_path, logger)
    logger.debug(f"Znaková sada XML souboru: {encoding}")

    # Check doctype and bmecat tags
    if check_bmecat_and_doctype(file_path, logger, encoding):
        try:
            stream_bmecat_to_csv(
                file_path=file_path,
                file_name=file_name,
                logger=logger,
                batch_size=batch_size,
            )
        except ET.ParseError as e:
            logger.error(f"Chyba v XML souboru: {e}")
        except Exception as e:
            logger.error(f"Chyba funkce xml_parse: {e}")
            logger.error(traceback.format_exc())
    else:
        logger.warning(f"Pokus jako obecný xml soubor")
        try:
            save_generic_xml_stream(file_path, file_name, logger)
        except ET.ParseError as e:
            logger.error(f"Chyba v XML souboru: {e}")
        except Exception as e:
            logger.error(f"Chyba funkce save_generic_xml_stream: {e}")
            logger.error(traceback.format_exc())

# Vrátí encoding deklarovaný v XML prologu.
# Pokud encoding není uveden, vrátí encoding odvozený z BOM nebo výchozí UTF-8.
def get_xml_declared_encoding(file_path, logger):
    default_encoding = 'utf-8'

    try:
        with open(file_path, 'rb') as file:
            raw_content = file.read(4096)
    except OSError as e:
        logger.error(f"Soubor se nepodařilo otevřít: {e}")
        return default_encoding

    fallback_encoding = default_encoding

    if raw_content.startswith(b'\xef\xbb\xbf'):
        fallback_encoding = 'utf-8-sig'
        content = raw_content.decode('utf-8-sig', errors='replace')
    elif raw_content.startswith(b'\xff\xfe') or raw_content.startswith(b'\xfe\xff'):
        fallback_encoding = 'utf-16'
        content = raw_content.decode('utf-16', errors='replace')
    elif raw_content.startswith(b'\x00<\x00?\x00x\x00m\x00l'):
        fallback_encoding = 'utf-16-be'
        content = raw_content.decode('utf-16-be', errors='replace')
    elif raw_content.startswith(b'<\x00?\x00x\x00m\x00l\x00'):
        fallback_encoding = 'utf-16-le'
        content = raw_content.decode('utf-16-le', errors='replace')
    else:
        # XML deklarace je ASCII kompatibilní, takže pro zjištění encodingu stačí ASCII.
        content = raw_content.decode('ascii', errors='ignore')

    prolog_pattern = (
        r'^\s*<\?xml\s+version\s*=\s*["\']1\.[0-9]["\']'
        r'(?:\s+encoding\s*=\s*["\'](?P<encoding>[A-Za-z][A-Za-z0-9._-]*)["\'])?'
        r'(?:\s+standalone\s*=\s*["\'](?P<standalone>yes|no)["\'])?'
        r'\s*\?>'
    )

    prolog_match = re.search(prolog_pattern, content, re.IGNORECASE)

    if not prolog_match:
        logger.warning(f"XML prolog nenalezen. Použije se znaková sada: {fallback_encoding}")
        return fallback_encoding

    declared_encoding = prolog_match.group('encoding')
    standalone = prolog_match.group('standalone')

    logger.debug(f"XML prolog: {prolog_match.group(0).strip()}")

    if standalone:
        logger.debug(f"Standalone atribut v prologu: {standalone}")

    if declared_encoding:
        logger.info(f"XML prolog obsahuje znakovou sadu: {declared_encoding}")
        return declared_encoding

    logger.warning(f"XML prolog neobsahuje znakovou sadu. Použije se: {fallback_encoding}")
    return fallback_encoding


# Check DOCTYPE & BMECAT tags
def check_bmecat_and_doctype(
    file_path,
    logger,
    encoding="utf-8",
    require_doctype: bool = False,
    allowed_versions: set[str] | tuple[str, ...] | list[str] | None = ("1.2", "2005", "2013"),
    allow_any_version: bool = False,
):
    """
    Validacni BMECAT kontrola.

    Defaultni doporucene chovani:
    - DOCTYPE chybi              -> warning, ale soubor muze projit
    - BMECAT chybi               -> False
    - version chybi              -> False
    - version neni v allowed     -> False
    - version je v allowed       -> True

    Defaultne jsou povolene verze 1.2, 2005 a 2013, protoze tyto priklady z praxe maji projit.

    Pokud require_doctype=True:
    - DOCTYPE chybi              -> False

    Pokud allow_any_version=True:
    - version musi existovat, ale nekontroluje se proti allowed_versions
    """

    doctype_pattern = re.compile(r"<!DOCTYPE\b[^<>]*>")
    bmecat_pattern = re.compile(r"<BMECAT\b[^<>]*>")
    version_pattern = re.compile(r"\bversion\s*=\s*(['\"])(.*?)\1")

    try:
        with open(file_path, "r", encoding=encoding) as file:
            content = file.read(4096)

        doctype_match = doctype_pattern.search(content)
        if not doctype_match:
            if require_doctype:
                logger.error("Nenalezen DOCTYPE")
                return False
            logger.warning("Nenalezen DOCTYPE - pokracuji, protoze neni povinny")
        else:
            logger.debug(f"DOCTYPE nalezen: {doctype_match.group(0)}")

        bmecat_match = bmecat_pattern.search(content)
        if not bmecat_match:
            logger.error("Nenalezen tag <BMECAT>")
            return False

        bmecat_content = bmecat_match.group(0)
        logger.debug(f"BMECAT nalezen: {bmecat_content}")

        version_match = version_pattern.search(bmecat_content)
        if not version_match:
            logger.error("BMECAT tag neobsahuje atribut version")
            return False

        version = version_match.group(2).strip()

        if allow_any_version:
            logger.info("BMECAT verze: %s", version)
            return True

        allowed_versions_set = set(allowed_versions or ())
        if version not in allowed_versions_set:
            logger.error(
                "Nepodporovana BMECAT verze: %s. Povolene verze: %s",
                version,
                ", ".join(sorted(allowed_versions_set)) or "zadne",
            )
            return False

        logger.info("BMECAT verze: %s", version)
        return True

    except UnicodeDecodeError as e:
        logger.error(f"Chyba kodovani souboru: {e}")
        return False
    except FileNotFoundError:
        logger.error(f"Soubor neexistuje: {file_path}")
        return False
    except Exception as e:
        logger.error(f"Chyba funkce check_bmecat_and_doctype_validated: {e}")
        return False


def _safe_remove_child(parent, element, logger):
    """
    Bezpečně odebere XML element z jeho rodiče.

    Používá se při streamovém zpracování XML, aby se již zpracované části
    neuvažovaly dál v paměti.
    """
    if parent is None:
        # Element nemá rodiče, není co odebírat.
        return

    try:
        # Odebere element z rodičovského elementu.
        parent.remove(element)

    except ValueError:
        # Element už v rodiči není.
        # To může nastat například při postupném čištění stromu.
        # Nejde o chybu, protože cílem je pouze uvolnit paměť.
        pass

    except Exception as exc:
        # Ostatní chyby pouze zalogujeme jako debug.
        # Zpracování kvůli tomu nepřerušujeme.
        logger.debug("Nepodařilo se uvolnit element z rodiče: %s", exc)


def iter_end_elements(file_path, wanted_tags, logger):
    """
    Streamově prochází XML soubor a vrací pouze vybrané elementy.

    Funkce používá ET.iterparse(), takže nenačítá celé XML do paměti.
    Vybraný element vrátí až ve chvíli, kdy je načten celý, tedy na END události.

    Po zpracování volajícím kódem se element vyčistí a odebere z rodiče,
    aby se v paměti nedržely již zpracované produkty.
    """
    # Převod na set kvůli rychlejšímu testování, zda tag patří mezi požadované.
    wanted_tags = set(wanted_tags)

    # Stack slouží ke sledování aktuální cesty v XML stromu.
    # Díky němu lze zjistit rodiče aktuálního elementu.
    stack = []

    # Příznak, jestli už byl načten kořenový element XML.
    root_seen = False

    # Iterparse čte XML postupně a vrací události "start" a "end".
    context = ET.iterparse(file_path, events=("start", "end"))

    for event, elem in context:
        if event == "start":
            # První start element je root XML dokumentu.
            if not root_seen:
                root_seen = True

                # Pokud tag obsahuje namespace ve formátu {namespace}TAG,
                # vytáhne se namespace a zaloguje.
                if '}' in elem.tag:
                    namespace = elem.tag.split('}')[0].strip('{')
                    logger.info(f"Namespace: {namespace}")
                else:
                    logger.info("Namespace nenalezen.")

            # Přidáme aktuální element na stack.
            stack.append(elem)
            continue

        # Při END události už je element kompletně načtený.
        # clean_tag pravděpodobně odstraní namespace, např. {ns}PRODUCT -> PRODUCT.
        tag = bme_parser.clean_tag(elem.tag)

        # Rodič aktuálního elementu je předposlední položka ve stacku.
        parent = stack[-2] if len(stack) > 1 else None

        if tag in wanted_tags:
            # Vrátíme volajícímu kódu název tagu a celý XML element.
            yield tag, elem

            # Po návratu z volajícího kódu se element vyčistí.
            # Tím se uvolní jeho text, atributy a potomci.
            elem.clear()

            # Element se zároveň odebere z rodiče,
            # aby zpracovaná část XML nezůstávala v paměti.
            _safe_remove_child(parent, elem, logger)

        # Po dokončení END události odebereme element ze stacku.
        if stack:
            stack.pop()


def stream_bmecat_to_csv(file_path, file_name, logger, batch_size=100):
    """
    Streamově převede BMEcat XML soubor do CSV výstupu.

    XML se zpracovává postupně přes iterparse, takže se celé nenačítá do RAM.
    Produkty lze zpracovávat buď sekvenčně, nebo paralelně pomocí více procesů.
    """

    # Ochrana proti neplatné velikosti dávky.
    # Minimum je vždy 1.
    batch_size = max(1, int(batch_size or 100))

    # Processor zajišťuje zpracování hlavičky, produktů a finální zápis.
    processor = bme_parser.BMEStreamProcessor(file_name, logger)
    
    try:
        # Sekvenční režim.
        # Vše se zpracovává v jednom procesu bez dávkování.
        for tag, element in iter_end_elements(file_path, {"HEADER", "PRODUCT", "ARTICLE"}, logger):
            if tag == "HEADER":
                processor.process_header(element)
                #logger.debug(f"processor.process_header_element: {ET.tostring(element, encoding="unicode")}")
            else:
                processor.process_product_element(element)
                #logger.debug(f"processor.process_product_element: {ET.tostring(element, encoding="unicode")}")

        # Uzavření výstupů, dopsání souborů, případné finální operace.
        processor.finalize()

        logger.info("XML soubor je validní.")

    except Exception:
        # Při chybě se provede úklid rozpracovaných výstupů.
        processor.cleanup()

        # Chyba se znovu vyvolá, aby ji mohl řešit nadřazený kód.
        raise


def save_generic_xml_stream(file_path, output_csv, logger):
    output_name = output_csv
    writer = bme_parser.DynamicCsvBuffer(output_name, logger)
    product_tags = {"item", "ITEM", "SHOPITEM", "PRODUCT"}

    try:
        for tag, product in iter_end_elements(file_path, product_tags, logger):
            product_data = {}
            for element in product:
                product_data[bme_parser.clean_tag(element.tag)] = element.text.strip() if element.text else ""
            writer.writerow(product_data)

        writer.finalize()
    except Exception:
        writer.cleanup()
        raise
