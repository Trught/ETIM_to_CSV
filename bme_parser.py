import os
import csv
import xml.etree.ElementTree as ET

# Remove namespace from tag
def clean_tag(tag):
    return tag.split("}", 1)[-1] if isinstance(tag, str) else tag

# Create a key from tag & attributes
def create_key(tag, attributes):
    if not attributes:
        return tag

    attr_parts = [f"@{key}:{value}" for key, value in sorted(attributes.items())]
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

# Parse HEADER
def parse_BME_header(root, file_name, logger):
    header = next(root.iterfind(".//HEADER"), None)
    if not header:
        logger.warning("Nenalezen HEADER v XML souboru.")
        return
    
    logger.info("Analýza HEADER dat.")
    parsed_header = parse_element(header, logger)
    
    catalog = parsed_header.get("CATALOG", {})
    lang_def = catalog.get("LANGUAGE @default:true", catalog.get("LANGUAGE", ""))
    
    logger.info("Výchozí jazyk: %s", lang_def)
    logger.debug("Header data: %s", parsed_header)
    
    flat_header = flatten_dict(parsed_header)
    save_to_csv(f"{file_name}_hlavicka", [flat_header], logger)

# Parse Products
def parse_BME_products(root, file_name, logger):
    all_product_entries, all_mime_entries, all_keyword_entries = [], [], []
    all_packing_entries, all_udx_logistics_entries = [], []
    all_feature_entries = []

    logger.info("Analýza PRODUCT + ARTICLE dat.")

    for product in list(root.iterfind(".//PRODUCT")) + list(root.iterfind(".//ARTICLE")):
        product_data = parse_element(product, logger)
        product_is_article = clean_tag(product.tag) == "ARTICLE"
         # Rozpoznání typu záznamu a sjednocení ARTICLE -> PRODUCT struktura
        if clean_tag(product.tag) == "ARTICLE":
            
            if "SUPPLIER_AID" in product_data:
                product_data["SUPPLIER_PID"] = product_data["SUPPLIER_AID"]

            if "ARTICLE_DETAILS" in product_data:
                product_data["PRODUCT_DETAILS"] = product_data["ARTICLE_DETAILS"]

            if "ARTICLE_FEATURES" in product_data:
                product_data["PRODUCT_FEATURES"] = product_data["ARTICLE_FEATURES"]
            
        supplier_pid = next((product_data[key] for key in product_data if key.startswith("SUPPLIER_PID")), "N/A")
        product_details = product_data.get("PRODUCT_DETAILS", {})
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
            logger.warning(f"EAN nenalezen u produktu {supplier_pid}")
        
        # Parse product details
        product_entries = parse_BME_product(product_data, logger)
        for entry in product_entries:
            entry["SUPPLIER_PID"] = supplier_pid
            all_product_entries.append(entry)

        # Parse MIME data
        mime_data = parse_BME_mime(product_data, logger)
        for entry in mime_data:
            entry["SUPPLIER_PID"] = supplier_pid
            entry["EAN"] = inter_pid_ean
            all_mime_entries.append(entry)

        # Parse Keywords
        keyword_entries = parse_BME_keyword(product_data, logger)
        all_keyword_entries.extend(keyword_entries)

        # ---- NEW: Parse UDX packing + logistics ----
        packing_units, udx_logistics = parse_udx_packing_and_logistics(product_data, logger)

        # packing_units is a list
        for pu in packing_units:
            pu["SUPPLIER_PID"] = supplier_pid
            pu["EAN"] = inter_pid_ean
            all_packing_entries.append(pu)

        # udx_logistics is a dict (single record)
        if udx_logistics:
            udx_logistics["SUPPLIER_PID"] = supplier_pid
            udx_logistics["EAN"] = inter_pid_ean
            all_udx_logistics_entries.append(udx_logistics)

        # NEW: Parse PRODUCT_FEATURES
        feature_entries = parse_BME_features(product_data, logger)
        for fe in feature_entries:
            fe["SUPPLIER_PID"] = supplier_pid
            fe["EAN"] = inter_pid_ean
            all_feature_entries.append(fe)


    save_to_csv(f"{file_name}_produkty", all_product_entries, logger)
    save_to_csv(f"{file_name}_soubory", all_mime_entries, logger)
    save_to_csv(f"{file_name}_klicova_slova", all_keyword_entries, logger)

    # NEW: packing units and logistics
    save_to_csv(f"{file_name}_jednotky_balení", all_packing_entries, logger)
    save_to_csv(f"{file_name}_udx_logistics", all_udx_logistics_entries, logger)
    save_to_csv(f"{file_name}_features", all_feature_entries, logger)

# Parse MIME    
def parse_BME_mime(data, logger):
    mime_entries = []
    valid_mime_codes = {
        "MD01": "Obrázek výrobku", #Product picture
        "MD02": "Podobný obrázek", #Similar figure
        "MD03": "Bezpečnostní list", #Safety data sheet
        "MD04": "Stránka produktu Deeplink", #Deeplink product page
        "MD05": "Deeplink REACH", #Deeplink REACH
        "MD06": "Energetický štítek", #Energy label
        "MD07": "Datový list výrobku pro energetický štítek", #Product data sheet for energy label
        "MD08": "Kalibrační certifikát", #Calibration certificate
        "MD09": "Certifikát", #Certificate
        "MD10": "Schéma zapojení", #Circuit diagram
        "MD11": "Regulace stavebních výrobků", #Construction Products Regulation
        "MD12": "Rozměrový výkres", #Dimensioned drawing
        "MD13": "Environmentální značka", #Environment label
        "MD14": "Návod k použití", #Instructions for use
        "MD15": "Diagram světelného kužele", #Light cone diagram
        "MD16": "Křivka distribuce světla", #Light Distribution Curve
        "MD17": "Logo 1c", #Logo 1c
        "MD18": "Logo 4c", #Logo 4c
        "MD19": "Luminaire data", #Luminaire data
        "MD20": "Obrázek prostředí", #Ambient picture
        "MD21": "Montážní pokyny", #Mounting instruction
        "MD22": "Datový list výrobku", #Product data sheet
        "MD23": "Obrázek produktu – zadní pohled", #Product picture back view
        "MD24": "Obrázek produktu – pohled zespodu", #Product picture bottom view
        "MD25": "Obrázek produktu – detailní pohled", #Product picture detailed view
        "MD26": "Obrázek produktu – přední pohled", #Product picture front view
        "MD27": "Obrázek produktu – šikmý pohled", #Product picture sloping
        "MD28": "Obrázek produktu – pohled shora", #Product picture top view
        "MD29": "Obrázek produktu – pohled z levé strany", #Product picture view from the left side
        "MD30": "Obrázek produktu – pohled z pravé strany", #Product picture view from the right side
        "MD31": "Osvědčení o schválení", #Seal of approval
        "MD32": "Technická příručka", #Technical manual
        "MD32_DE": "Technická příručka_DE", #Technical manual
        "MD33": "Schválení testu", #Test approval
        "MD34": "Schéma zapojení", #Wiring diagram
        "MD35": "Prohlášení dodavatele o preferenčním původu produktu", #Supplier’s declaration for products having preferential origin status
        "MD36": "Prohlášení", #Declaration, deleted in version 3.1 -> 4.0
        "MD37": "3D / BIM objekt", #3D / BIM object
        "MD38": "Dokumentace pro správu, provoz a údržbu", #Management, operation and maintenance document
        "MD39": "Instruktážní video", #Instructional video
        "MD40": "Seznam náhradních dílů", #Spare parts list
        "MD41": "Prodejní brožura", #Sales brochure
        "MD42": "AVCP Certifikát (Assessment and Verification of Constancy of Performance)", #AVCP certificate (Assessment and Verification of Constancy of Performance)
        "MD43": "CLP (Classification, Labelling and Packaging)", #CLP (Classification, Labelling and Packaging)
        "MD44": "ECOP (Environmental Code of Practice)", #ECOP (Environmental Code of Practice)
        "MD45": "Produktové video", #Product video
        "MD46": "360° pohled", #360° view
        "MD47": "Náhled obrázku produktu (MD01)", #Thumbnail of Product picture (MD01)
        "MD48": "Piktogram/Ikona", #Pictogram/Icon
        "MD49": "Prohlášení RoHS", #Declaration RoHS
        "MD50": "Prohlášení CoC (Certifikát shody, požadovaný pro CPR)", #Declaration CoC (Certificate of Conformity, requested for CPR)
        "MD51": "Prohlášení DOP (Prohlášení o vlastnostech)", #Declaration DOP (Declaration of performance)
        "MD52": "Prohlášení DOC CE (Prohlášení o shodě CE)", #Declaration DOC CE (Declaration of conformity CE)
        "MD53": "Prohlášení BREEAM (Metoda environmentálního hodnocení budov BREEAM)", #Declaration BREEAM (Building Research Establishment Environmental Assessment Method)
        "MD54": "Prohlášení EPD (Environmentální prohlášení o produktu)", #Declaration EPD (Environmental Product Declaration)
        "MD55": "Prohlášení ETA (Evropské technické posouzení)", #Declaration ETA (European Technical Assessment)
        "MD56": "Prohlášení o záruce (Záruční list)", #Declaration warranty (Warranty statement)
        "MD57": "Aplikační video", #Application video
        "MD58": "Otázky a odpovědi (Q&A video)", #Question and Answer (Q&A video)
        "MD59": "Obrázek produktu ve čtvercovém formátu", #Product picture square format
        "MD60": "Rozložený pohled (výkres)", #Exploded view drawing
        "MD61": "Vývojový diagram", #Flowchart
        "MD62": "Prezentace produktu", #Product presentation
        "MD63": "Specification text", #Specification text
        "MD64": "Line drawing", #Line drawing
        "MD65": "Pohled na produktovou řadu", #Product family view
        "MD99": "Ostatní" #Others
    }
    user_defined_extensions = data.get("USER_DEFINED_EXTENSIONS", {})
    if user_defined_extensions:
        mime_info = user_defined_extensions.get("UDX.EDXF.MIME_INFO", {})
        if mime_info:
            mime_data = mime_info.get("UDX.EDXF.MIME", [])
            if isinstance(mime_data, dict):
                mime_entries.append(mime_data)
            elif isinstance(mime_data, list):
                mime_entries.extend(mime_data)
    
    # Extract from MIME_INFO (fallback)
    logger.debug("Hledám MIME_INFO v hlavní struktuře.")
    mime_info = data.get("MIME_INFO", {})
    if mime_info:
        mime_data = mime_info.get("MIME", [])    
        if isinstance(mime_data, dict):
            mime_entries.append(mime_data)
        elif isinstance(mime_data, list):
            mime_entries.extend(mime_data)
    
    # Process MIME attributes
    for entry in mime_entries:
        if isinstance(entry, dict):
            mime_code = entry.get("MIME_CODE") or entry.get("UDX.EDXF.MIME_CODE")
            if not mime_code:
                logger.debug(f"MIME_CODE nenalezen, hledám v MIME_DESCR ")
                mime_code = entry.get("MIME_DESCR")
            if mime_code:
                if mime_code not in valid_mime_codes:
                    logger.debug(f"Neplatný MIME_CODE: {mime_code}")
                else:
                    entry["MIME_CODE_NAME"] = valid_mime_codes[mime_code]
            
            mime_source = entry.get("UDX.EDXF.MIME_SOURCE")
            if isinstance(mime_source, list) and len(mime_source) == 2 and mime_source[0] == mime_source[1]:
                entry["UDX.EDXF.MIME_SOURCE"] = mime_source[0]
            
            for key, value in list(entry.items()):
                if isinstance(value, dict) and '@lang' in value:
                    entry[f"{key} @lang:{value['@lang']}"] = value['#text']
                    del entry[key]
    
    return mime_entries


# Parse Product Details
def parse_BME_product(product_data, logger):
    product_entry  = {}
    product_details = product_data.get("PRODUCT_DETAILS", {})
    product_logistic_details = product_data.get("PRODUCT_LOGISTIC_DETAILS", {})
    
    # Parse Product Logistic Details
    if product_logistic_details:
        custom_tariff_number = product_logistic_details.get("CUSTOMS_TARIFF_NUMBER", {})
        country_of_origin = product_logistic_details.get("COUNTRY_OF_ORIGIN", {})
        if custom_tariff_number:
            custom_number = custom_tariff_number.get("CUSTOMS_NUMBER", {})
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


# NEW: FEATURES 
def parse_BME_features(product_data, logger):
    features_block = product_data.get("PRODUCT_FEATURES", {})
    if not isinstance(features_block, dict) or not features_block:
        return []
    # FEATURE-Container kann auch "FEATURE @...:..." heißen -> iterieren
    feature_nodes = []
    for k, v in features_block.items():
        tag, _ = split_key(k)
        if tag == "FEATURE":
            feature_nodes = v
            break

    if not feature_nodes:
        return []

    if isinstance(feature_nodes, dict):
        feature_nodes = [feature_nodes]
    elif not isinstance(feature_nodes, list):
        return []

    # optionale Meta-Daten auf Block-Level
    ref_system_name, _ = get_first_value(features_block, "REFERENCE_FEATURE_SYSTEM_NAME")
    ref_group_id, _    = get_first_value(features_block, "REFERENCE_FEATURE_GROUP_ID")

    out = []

    for f in feature_nodes:
        if not isinstance(f, dict):
            continue

        # FNAME (Feature-Name)
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

        funit  = sanitize_value(funit_val)
        forder = sanitize_value(forder_val)

        # FVALUE: kann mehrfach vorkommen und hat oft @lang
        fvalue_items = iter_tag_values(f, "FVALUE")

        if not fvalue_items:
            out.append({
                "REFERENCE_FEATURE_SYSTEM_NAME": sanitize_value(ref_system_name),
                "REFERENCE_FEATURE_GROUP_ID": sanitize_value(ref_group_id),
                "FNAME": fname,
                "FNAME_LANG": fname_lang,
                "FVALUE": None,
                "FVALUE_LANG": None,
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
            attrs[a] = v
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


# NEW: UDX 
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