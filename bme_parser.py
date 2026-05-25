import time
import csv
import json
import os
import uuid
import xml.etree.ElementTree as ET
from urllib.parse import quote, unquote


# Slovník MIME kódů 
_VALID_MIME_CODES = {
    "MD01": "Obrázek výrobku",  # Product picture
    "MD02": "Podobný obrázek",  # Similar figure
    "MD03": "Bezpečnostní list",  # Safety data sheet
    "MD04": "Stránka produktu Deeplink",  # Deeplink product page
    "MD05": "Deeplink REACH",  # Deeplink REACH
    "MD06": "Energetický štítek",  # Energy label
    "MD07": "Datový list výrobku pro energetický štítek",  # Product data sheet for energy label
    "MD08": "Kalibrační certifikát",  # Calibration certificate
    "MD09": "Certifikát",  # Certificate
    "MD10": "Schéma zapojení",  # Circuit diagram
    "MD11": "Regulace stavebních výrobků",  # Construction Products Regulation
    "MD12": "Rozměrový výkres",  # Dimensioned drawing
    "MD13": "Environmentální značka",  # Environment label
    "MD14": "Návod k použití",  # Instructions for use
    "MD15": "Diagram světelného kužele",  # Light cone diagram
    "MD16": "Křivka distribuce světla",  # Light Distribution Curve
    "MD17": "Logo 1c",  # Logo 1c
    "MD18": "Logo 4c",  # Logo 4c
    "MD19": "Luminaire operating instructions",  # Luminaire operating instructions
    "MD20": "Luminaire installation instructions",  # Luminaire installation instructions
    "MD21": "Reach Manufacturer",  # Reach Manufacturer
    "MD22": "Energy label old",  # Energy label old
    "MD23": "Product fiche old",  # Product fiche old
    "MD24": "EPREL",  # EPREL
    "MD25": "Montážní pokyny",  # Mounting instructions
    "MD26": "Prohlášení o shodě",  # Declaration of Conformity
    "MD27": "Datový list",  # Data sheet
    "MD28": "Technický výkres",  # Technical drawing
    "MD29": "Provozní pokyny",  # Operating instructions
    "MD30": "Průvodce rychlým startem",  # Quick start guide
    "MD31": "FAQ",  # FAQ
    "MD32": "Kalibrační pokyny",  # Calibration instructions
    "MD33": "CAD data",  # CAD data
    "MD34": "BIM data",  # BIM data
    "MD35": "Bílý dokument",  # White paper
    "MD36": "Certifikace výrobku",  # Product certification
    "MD37": "Environmentální prohlášení",  # Environmental declaration
    "MD38": "EPD",  # EPD
    "MD39": "Návod k údržbě",  # Maintenance instructions
    "MD40": "Návod k opravě",  # Repair instructions
    "MD41": "Prohlášení CE",  # CE declaration
    "MD42": "AVCP certifikát (Assessment and Verification of Constancy of Performance)",
    "MD43": "CLP (Classification, Labelling and Packaging)",
    "MD44": "ECOP (Environmental Code of Practice)",
    "MD45": "Produktové video",  # Product video
    "MD46": "360° pohled",  # 360° view
    "MD47": "Náhled obrázku produktu (MD01)",  # Thumbnail of Product picture (MD01)
    "MD48": "Piktogram/Ikona",  # Pictogram/Icon
    "MD49": "Prohlášení RoHS",  # Declaration RoHS
    "MD50": "Prohlášení CoC (Certifikát shody, požadovaný pro CPR)",
    "MD51": "Prohlášení DOP (Prohlášení o vlastnostech)",
    "MD52": "Prohlášení DOC CE (Prohlášení o shodě CE)",
    "MD53": "Prohlášení BREEAM (Metoda environmentálního hodnocení budov BREEAM)",
    "MD54": "Prohlášení EPD (Environmentální prohlášení o produktu)",
    "MD55": "Prohlášení ETA (Evropské technické posouzení)",
    "MD56": "Prohlášení o záruce (Záruční list)",
    "MD57": "Aplikační video",  # Application video
    "MD58": "Otázky a odpovědi (Q&A video)",
    "MD59": "Obrázek produktu ve čtvercovém formátu",
    "MD60": "Rozložený pohled (výkres)",
    "MD61": "Vývojový diagram",
    "MD62": "Prezentace produktu",
    "MD63": "Specification text",
    "MD64": "Line drawing",
    "MD65": "Pohled na produktovou řadu",
    "MD99": "Ostatní",  # Others
}

# Limit repetitive debug spam for frequently occurring parser situations.
_DEBUG_EVENT_COUNTS = {}
_DEBUG_EVENT_LIMIT = 10


def _debug_limited(logger, event_key, message):
    count = _DEBUG_EVENT_COUNTS.get(event_key, 0)
    if count < _DEBUG_EVENT_LIMIT:
        logger.debug(message)
        count += 1
        _DEBUG_EVENT_COUNTS[event_key] = count
        if count == _DEBUG_EVENT_LIMIT:
            logger.debug(
                "Další opakování zprávy '%s' bude potlačeno.",
                event_key,
            )
    else:
        _DEBUG_EVENT_COUNTS[event_key] = count + 1

# Remove namespace from tag
def clean_tag(tag):
    return tag.split("}", 1)[-1] if isinstance(tag, str) else tag


# Create a key from tag & attributes
def create_key(tag, attributes):
    if not attributes:
        return tag

    # Escape attribute values so split_key() can round-trip even with spaces/colons.
    attr_parts = [f"@{quote(str(key), safe='')}:{quote(str(value), safe='')}" for key, value in sorted(attributes.items())]
    return f"{tag} {' '.join(attr_parts)}"


# Recursive XML Parsing
def parse_element(element, logger):
    if element is None:
        logger.warning("Element nenalezen (None).")
        return None

    parsed_data = {}
    # Process a single child element.
    for child in element:
        tag = clean_tag(child.tag)
        combined_key = create_key(tag, child.attrib)
        # Recursively parse child elements
        child_data = parse_element(child, logger) if len(child) else (child.text.strip() if child.text else None)
        # Handle multiple occurrences of the same key
        if combined_key in parsed_data:
            if not isinstance(parsed_data[combined_key], list):
                parsed_data[combined_key] = [parsed_data[combined_key]]
            parsed_data[combined_key].append(child_data)
        else:
            parsed_data[combined_key] = child_data

    return parsed_data


# Flatten nested dictionary
def flatten_dict(d, parent_key="", sep="_"):
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            for i, item in enumerate(v):
                items.extend(flatten_dict(item, f"{new_key}_{i}", sep=sep).items()) if isinstance(item, dict) else items.append((f"{new_key}_{i}", item))
        else:
            items.append((new_key, v))
    return dict(items)

# Disk-backed CSV writer for streamed XML processing.
class DynamicCsvBuffer:

    def __init__(self, file_name, logger, priority_fields=("SUPPLIER_PID",)):
        self.file_name = file_name
        self.logger = logger
        self.priority_fields = tuple(priority_fields)
        self.fieldnames = set()
        self._seen_fieldnames = set()
        self.row_count = 0

        os.makedirs("output", exist_ok=True)
        self.csv_file = os.path.join("output", f"{file_name}.csv")
        self._tmp_file = os.path.join("output", f".{file_name}.{uuid.uuid4().hex}.rows.jsonl")
        self._handle = open(self._tmp_file, "w", encoding="utf-8", newline="")
        self._closed = False

    def writerow(self, row):
        if not row:
            return
        normalized_row = {str(key): value for key, value in row.items()}
        new_fields = sorted(field for field in normalized_row.keys() if field not in self._seen_fieldnames)
        if new_fields:
            self.logger.debug(
                "Nové sloupce ve %s na řádku %s: %s",
                self.file_name,
                self.row_count + 1,
                ", ".join(new_fields),
            )
            self._seen_fieldnames.update(new_fields)
        self.fieldnames.update(normalized_row.keys())
        json.dump(normalized_row, self._handle, ensure_ascii=False, default=str)
        self._handle.write("\n")
        self.row_count += 1

    def writerows(self, rows):
        for row in rows or []:
            self.writerow(row)

    def _ordered_fieldnames(self):
        ordered = [field for field in self.priority_fields if field in self.fieldnames]
        ordered.extend(sorted(field for field in self.fieldnames if field not in ordered))
        return ordered

    def close_temp(self):
        if not self._closed:
            self._handle.close()
            self._closed = True

    def finalize(self):
        self.close_temp()

        if not self.row_count:
            self.cleanup()
            self.logger.warning(f"Žádná data k uložení: {self.file_name}.csv")
            return

        fieldnames = self._ordered_fieldnames()
        tmp_csv = f"{self.csv_file}.{uuid.uuid4().hex}.tmp"

        with open(tmp_csv, "w", newline="", encoding="utf-8") as csv_file, \
                open(self._tmp_file, "r", encoding="utf-8") as rows_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            for line in rows_file:
                writer.writerow(json.loads(line))

        os.replace(tmp_csv, self.csv_file)
        self.cleanup()
        self.logger.info(f"Uložen soubor: {self.csv_file}")

    def cleanup(self):
        self.close_temp()
        try:
            if os.path.exists(self._tmp_file):
                os.remove(self._tmp_file)
        except OSError as exc:
            self.logger.warning("Nepodařilo se odstranit dočasný soubor %s: %s", self._tmp_file, exc)


# Generic CSV Writing Function
def save_to_csv(file_name, data, logger):
    if not data:
        logger.warning(f"Žádná data k uložení: {file_name}.csv")
        return

    os.makedirs("output", exist_ok=True)
    csv_file = f'output/{file_name}.csv'

    # Collect column headers dynamically
    fieldnames = sorted({key for row in data for key in row.keys()})
    if 'SUPPLIER_PID' in fieldnames:
        fieldnames.remove('SUPPLIER_PID')  # Remove it temporarily
        fieldnames = ['SUPPLIER_PID'] + fieldnames  # Add it as the first column

    with open(csv_file, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

    logger.info(f"Uložen soubor: {csv_file}")


# Parse HEADER from a streamed element
def parse_BME_header_element(header, file_name, logger):
    if header is None:
        logger.warning("Nenalezen HEADER v XML souboru.")
        return

    logger.info("Analýza HEADER dat.")
    parsed_header = parse_element(header, logger)

    catalog = parsed_header.get("CATALOG", {}) if isinstance(parsed_header, dict) else {}
    if not isinstance(catalog, dict):
        catalog = {}
    lang_def = catalog.get("LANGUAGE @default:true", catalog.get("LANGUAGE", ""))

    logger.info("Výchozí jazyk: %s", lang_def)
    logger.debug("Header data: %s", parsed_header)

    flat_header = flatten_dict(parsed_header)
    save_to_csv(f"{file_name}_hlavicka", [flat_header], logger)

# Writes streamed BMEcat/ETIM rows without collecting products in RAM.
class BMEStreamProcessor:
    
    def __init__(self, file_name, logger):
        self.file_name = file_name
        self.logger = logger
        self.product_count = 0
        self.article_count = 0
        self.header_written = False
        self._writers = {
            "products": DynamicCsvBuffer(f"{file_name}_produkty", logger),
            "mimes": DynamicCsvBuffer(f"{file_name}_soubory", logger),
            "keywords": DynamicCsvBuffer(f"{file_name}_klicova_slova", logger),
            "packing": DynamicCsvBuffer(f"{file_name}_jednotky_balení", logger),
            "udx_logistics": DynamicCsvBuffer(f"{file_name}_udx_logistics", logger),
            "features": DynamicCsvBuffer(f"{file_name}_features", logger),
        }

    def process_header(self, header_element):
        if self.header_written:
            return
        parse_BME_header_element(header_element, self.file_name, self.logger)
        self.header_written = True

    def process_product_element(self, product_element):
        start_time = time.perf_counter()

        bundle = parse_BME_product_bundle(product_element, self.logger)
        self.write_product_bundle(bundle)

        duration_ms = (time.perf_counter() - start_time) * 1000
        if duration_ms >= 20:
            self.logger.warning("Dlouhá doba zpracování produktu: %.2f ms, SUPPLIER_PID=%s", duration_ms, bundle.get("supplier_pid", "N/A"))
        
        if bundle:
            self.logger.debug(
                "Produkt zpracován: tag=%s, SUPPLIER_PID=%s, duration=%.2f ms",
                bundle.get("record_tag", clean_tag(product_element.tag)),
                bundle.get("supplier_pid", "N/A"),
                duration_ms,
            )

    def write_product_bundle(self, bundle):
        if not bundle:
            return
        self._writers["products"].writerows(bundle.get("products", []))
        self._writers["mimes"].writerows(bundle.get("mimes", []))
        self._writers["keywords"].writerows(bundle.get("keywords", []))
        self._writers["packing"].writerows(bundle.get("packing", []))
        self._writers["udx_logistics"].writerows(bundle.get("udx_logistics", []))
        self._writers["features"].writerows(bundle.get("features", []))
        self.product_count += int(bundle.get("product_count", 0))
        self.article_count += int(bundle.get("article_count", 0))

    def finalize(self):
        if not self.header_written:
            self.logger.warning("Nenalezen HEADER v XML souboru.")
        for writer in self._writers.values():
            writer.finalize()
        self.logger.info(
            "Zpracováno záznamů: PRODUCT=%s, ARTICLE=%s",
            self.product_count,
            self.article_count,
        )

    def cleanup(self):
        for writer in self._writers.values():
            writer.cleanup()


def parse_BME_product_bundle(product, logger):
    product_data = parse_element(product, logger)
    product_tag = clean_tag(product.tag)
    return parse_BME_product_bundle_from_data(product_data, product_tag, logger)


def parse_BME_product_bundle_from_data(product_data, product_tag, logger):
    product_entries, mime_entries, keyword_entries = [], [], []
    packing_entries, udx_logistics_entries, feature_entries = [], [], []

    if not isinstance(product_data, dict):
        product_data = {}

    product_is_article = clean_tag(product_tag) == "ARTICLE"
    # Rozpoznání typu záznamu a sjednocení ARTICLE -> PRODUCT struktura
    if product_is_article:
        if "SUPPLIER_AID" in product_data:
            product_data["SUPPLIER_PID"] = product_data["SUPPLIER_AID"]

        if "ARTICLE_DETAILS" in product_data:
            product_data["PRODUCT_DETAILS"] = product_data["ARTICLE_DETAILS"]

        if "ARTICLE_FEATURES" in product_data:
            product_data["PRODUCT_FEATURES"] = product_data["ARTICLE_FEATURES"]

        if "ARTICLE_LOGISTIC_DETAILS" in product_data:
            product_data["PRODUCT_LOGISTIC_DETAILS"] = product_data["ARTICLE_LOGISTIC_DETAILS"]

    supplier_pid = next((product_data[key] for key in product_data if key.startswith("SUPPLIER_PID")), "N/A")
    product_details = product_data.get("PRODUCT_DETAILS", {})
    if not isinstance(product_details, dict):
        product_details = {}

    logger.debug(f"Zpracovávám produkt:{supplier_pid}")
    if product_is_article:
        logger.warning(f"ARTICLE zpracován jako produkt: {supplier_pid}")

    # EAN parse
    # Normalize keys for case-insensitive matching
    product_details_lower = {key.lower(): value for key, value in product_details.items()}
    ean_keys = ["ean", "international_pid @type:ean", "international_pid @type:gtin"]
    inter_pid_ean = next((product_details_lower[key] for key in ean_keys if key in product_details_lower), None)
    logger.debug(f"EAN: {inter_pid_ean}")
    if not inter_pid_ean:
        logger.debug(f"EAN nenalezen u produktu {supplier_pid}")

    # Parse product details
    for entry in parse_BME_product(product_data, logger):
        entry["SUPPLIER_PID"] = supplier_pid
        product_entries.append(entry)

    # Parse MIME data
    for entry in parse_BME_mime(product_data, logger):
        entry["SUPPLIER_PID"] = supplier_pid
        entry["EAN"] = inter_pid_ean
        mime_entries.append(entry)

    # Parse Keywords
    keyword_entries.extend(parse_BME_keyword(product_data, logger))

    # Parse UDX packing + logistics
    packing_units, udx_logistics = parse_udx_packing_and_logistics(product_data, logger)

    # packing_units is a list
    for pu in packing_units:
        pu["SUPPLIER_PID"] = supplier_pid
        pu["EAN"] = inter_pid_ean
        packing_entries.append(pu)

    # udx_logistics is a dict (single record)
    if udx_logistics:
        udx_logistics["SUPPLIER_PID"] = supplier_pid
        udx_logistics["EAN"] = inter_pid_ean
        udx_logistics_entries.append(udx_logistics)

    # Parse PRODUCT_FEATURES
    for fe in parse_BME_features(product_data, logger):
        fe["SUPPLIER_PID"] = supplier_pid
        fe["EAN"] = inter_pid_ean
        feature_entries.append(fe)

    return {
        "products": product_entries,
        "mimes": mime_entries,
        "keywords": keyword_entries,
        "packing": packing_entries,
        "udx_logistics": udx_logistics_entries,
        "features": feature_entries,
        "product_count": 0 if product_is_article else 1,
        "article_count": 1 if product_is_article else 0,

        # Metadata pouze pro debug logování výkonu.
        # Do CSV se nezapisují, protože write_product_bundle() bere jen datové sekce výše.
        "supplier_pid": supplier_pid,
        "record_tag": "ARTICLE" if product_is_article else "PRODUCT",
    }


# Parse MIME
def parse_BME_mime(data, logger):
    raw_mime_entries = []
    user_defined_extensions = data.get("USER_DEFINED_EXTENSIONS", {})
    if user_defined_extensions:
        mime_info = user_defined_extensions.get("UDX.EDXF.MIME_INFO", {})
        if mime_info:
            mime_data = mime_info.get("UDX.EDXF.MIME", [])
            if isinstance(mime_data, dict):
                raw_mime_entries.append(mime_data)
            elif isinstance(mime_data, list):
                raw_mime_entries.extend(mime_data)

    # Extract from MIME_INFO (fallback)
    logger.debug("Hledám MIME_INFO v hlavní struktuře.")
    mime_info = data.get("MIME_INFO", {})
    if mime_info:
        mime_data = mime_info.get("MIME", [])
        if isinstance(mime_data, dict):
            raw_mime_entries.append(mime_data)
        elif isinstance(mime_data, list):
            raw_mime_entries.extend(mime_data)

    # Process MIME attributes
    mime_entries = []
    for raw_entry in raw_mime_entries:
        if isinstance(raw_entry, dict):
            entry = dict(raw_entry)
            mime_code = entry.get("MIME_CODE") or entry.get("UDX.EDXF.MIME_CODE")
            if not mime_code:
                _debug_limited(logger, "mime_code_missing", "MIME_CODE nenalezen, hledám v MIME_DESCR")
                mime_code = entry.get("MIME_DESCR")
            
            if mime_code:
                mime_code_name = _VALID_MIME_CODES.get(mime_code)
                if mime_code_name:
                    entry["MIME_CODE_NAME"] = mime_code_name
                else:
                    _debug_limited(logger, f"invalid_mime_code:{mime_code}", f"Neplatný MIME_CODE: {mime_code}")

            mime_source = entry.get("UDX.EDXF.MIME_SOURCE")
            if isinstance(mime_source, list) and len(mime_source) == 2 and mime_source[0] == mime_source[1]:
                entry["UDX.EDXF.MIME_SOURCE"] = mime_source[0]

            for key, value in list(entry.items()):
                if isinstance(value, dict) and '@lang' in value:
                    entry[f"{key} @lang:{value['@lang']}"] = value['#text']
                    del entry[key]
            mime_entries.append(entry)

    return mime_entries


# Parse Product Details
def parse_BME_product(product_data, logger):
    product_entry = {}
    product_details = product_data.get("PRODUCT_DETAILS", {})
    product_logistic_details = product_data.get("PRODUCT_LOGISTIC_DETAILS", {})

    if not isinstance(product_details, dict):
        product_details = {}
    if not isinstance(product_logistic_details, dict):
        product_logistic_details = {}

    # Parse Product Logistic Details
    if product_logistic_details:
        custom_tariff_number = product_logistic_details.get("CUSTOMS_TARIFF_NUMBER", {})
        country_of_origin = product_logistic_details.get("COUNTRY_OF_ORIGIN", {})
        if custom_tariff_number:
            custom_number = custom_tariff_number.get("CUSTOMS_NUMBER", {}) if isinstance(custom_tariff_number, dict) else None
            if custom_number:
                product_entry["CUSTOMS_TARIFF_NUMBER"] = custom_number
        if country_of_origin:
            product_entry["COUNTRY_OF_ORIGIN"] = country_of_origin

    for tag, value in product_details.items():
        if isinstance(value, list):  # Convert lists to comma-separated strings
            value = ", ".join(map(str, value))
        product_entry[tag] = sanitize_value(value)

    return [product_entry]


# Parse Keywords
def parse_BME_keyword(product_data, logger):
    supplier_pid = next((product_data[key] for key in product_data if key.startswith("SUPPLIER_PID")), "N/A")
    product_details = product_data.get("PRODUCT_DETAILS", {})
    if not isinstance(product_details, dict):
        return []

    result = []
    for tag, value in product_details.items():
        if not tag.startswith("KEYWORD") or not value:
            continue

        if isinstance(value, list):
            value = ", ".join(map(str, value))
        elif isinstance(value, dict):
            value = str(value)

        result.append({
            "SUPPLIER_PID": supplier_pid,
            "keyword_tag": tag,
            "keyword_value": sanitize_value(value)
        })
    return result


# FEATURES
def parse_BME_features(product_data, logger):
    feature_blocks = []
    for key, value in product_data.items():
        tag, _ = split_key(key)
        if tag != "PRODUCT_FEATURES":
            continue
        if isinstance(value, dict):
            feature_blocks.append(value)
        elif isinstance(value, list):
            feature_blocks.extend(item for item in value if isinstance(item, dict))

    if not feature_blocks:
        return []

    out = []
    for features_block in feature_blocks:
        feature_nodes = []
        for k, v in features_block.items():
            tag, _ = split_key(k)
            if tag != "FEATURE":
                continue
            if isinstance(v, dict):
                feature_nodes.append(v)
            elif isinstance(v, list):
                feature_nodes.extend(item for item in v if isinstance(item, dict))

        if not feature_nodes:
            continue

        # optional meta-data on block-level
        ref_system_name, _ = get_first_value(features_block, "REFERENCE_FEATURE_SYSTEM_NAME")
        ref_group_id, _ = get_first_value(features_block, "REFERENCE_FEATURE_GROUP_ID")

        for f in feature_nodes:
            if not isinstance(f, dict):
                continue

            # FNAME (Feature name)
            fname_candidates = iter_tag_values(f, "FNAME")
            if fname_candidates:
                fname_val, fname_attrs = fname_candidates[0]
                fname = sanitize_value(fname_val)
                fname_lang = fname_attrs.get("lang") or fname_attrs.get("xml:lang")
            else:
                fname, fname_lang = None, None

            # optional
            funit_val, _ = get_first_value(f, "FUNIT")
            forder_val, _ = get_first_value(f, "FORDER")
            fvalue_details_val, _ = get_first_value(f, "FVALUE_DETAILS")

            funit = sanitize_value(funit_val)
            forder = sanitize_value(forder_val)
            fvalue_details = sanitize_value(fvalue_details_val)

            # FVALUE can occur multiple times and often carries @lang.
            fvalue_items = iter_tag_values(f, "FVALUE")

            if not fvalue_items:
                out.append({
                    "REFERENCE_FEATURE_SYSTEM_NAME": sanitize_value(ref_system_name),
                    "REFERENCE_FEATURE_GROUP_ID": sanitize_value(ref_group_id),
                    "FNAME": fname,
                    "FNAME_LANG": fname_lang,
                    "FVALUE": None,
                    "FVALUE_LANG": None,
                    "FVALUE_DETAILS": fvalue_details,
                    "FUNIT": funit,
                    "FORDER": forder
                })
                continue

            for fval, fattrs in fvalue_items:
                fvalue_lang = fattrs.get("lang") or fattrs.get("xml:lang")
                out.append({
                    "REFERENCE_FEATURE_SYSTEM_NAME": sanitize_value(ref_system_name),
                    "REFERENCE_FEATURE_GROUP_ID": sanitize_value(ref_group_id),
                    "FNAME": fname,
                    "FNAME_LANG": fname_lang,
                    "FVALUE": sanitize_value(fval),
                    "FVALUE_LANG": fvalue_lang,
                    "FVALUE_DETAILS": fvalue_details,
                    "FUNIT": funit,
                    "FORDER": forder
                })
    return out


def split_key(k: str):
    # "FVALUE @lang:de @type:x" -> ("FVALUE", {"lang":"de","type":"x"})
    parts = str(k).split()
    tag = parts[0] if parts else ""
    attrs = {}
    for p in parts[1:]:
        if p.startswith("@") and ":" in p[1:]:
            a, v = p[1:].split(":", 1)
            attrs[unquote(a)] = unquote(v)
    return tag, attrs


def get_first_value(d: dict, wanted_tag: str):
    if not isinstance(d, dict):
        return None, None
    for k, v in d.items():
        tag, attrs = split_key(k)
        if tag == wanted_tag:
            return v, attrs
    return None, None


def iter_tag_values(d: dict, wanted_tag: str):
    """
    Liefert Liste von (value, attrs) für alle Keys, deren Tag = wanted_tag ist.
    Berücksichtigt Listenwerte.
    """
    out = []
    if not isinstance(d, dict):
        return out

    for k, v in d.items():
        tag, attrs = split_key(k)
        if tag != wanted_tag:
            continue

        if isinstance(v, list):
            for item in v:
                out.append((item, attrs))
        else:
            out.append((v, attrs))
    return out


def sanitize_value(value):
    if isinstance(value, str):
        return value.replace("\n", " ").replace("\r", " ").strip()
    return value


# UDX
def strip_udx_prefix(s: str) -> str:
    if isinstance(s, str) and s.startswith("UDX.EDXF."):
        return s.split("UDX.EDXF.", 1)[1]
    return s


def normalize_lang_nodes(d: dict):
    # stejná logika jako u MIME: {'@lang': 'de', '#text': '...'} -> 'key @lang:de': '...'
    for key, value in list(d.items()):
        if isinstance(value, dict) and '@lang' in value and '#text' in value:
            d[f"{key} @lang:{value['@lang']}"] = value['#text']
            del d[key]


def flatten_udx_dict(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        nk = strip_udx_prefix(k)
        if isinstance(v, dict) and '#text' in v:
            out[nk] = v.get('#text')
            if '@lang' in v:
                out[f"{nk} @lang:{v.get('@lang')}"] = v.get('#text')
        elif isinstance(v, (str, int, float, bool)) or v is None:
            out[nk] = v
        else:
            # nested dict/list: podle potřeby ponechat v surovém stavu nebo ignorovat
            out[nk] = v
    normalize_lang_nodes(out)
    return out


def parse_udx_packing_and_logistics(data, logger):
    packing_units = []
    udx_logistics = {}

    user_defined_extensions = data.get("USER_DEFINED_EXTENSIONS", {})
    if user_defined_extensions:
        # PACKING_UNITS
        pu_container = user_defined_extensions.get("UDX.EDXF.PACKING_UNITS", {})
        if isinstance(pu_container, dict):
            pu = pu_container.get("UDX.EDXF.PACKING_UNIT", [])
            if isinstance(pu, dict):
                packing_units.append(flatten_udx_dict(pu))
            elif isinstance(pu, list):
                for item in pu:
                    if isinstance(item, dict):
                        packing_units.append(flatten_udx_dict(item))

        # PRODUCT_LOGISTIC_DETAILS
        pld = user_defined_extensions.get("UDX.EDXF.PRODUCT_LOGISTIC_DETAILS", {})
        if isinstance(pld, dict) and pld:
            udx_logistics = flatten_udx_dict(pld)

    return packing_units, udx_logistics
