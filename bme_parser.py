import os
import csv
import xml.etree.ElementTree as ET

# Remove namespace from tag
def clean_tag(tag):
    return tag.split('}')[-1]

# Create a key from tag & attributes
def create_key(tag, attributes):
    if attributes:
        attr_parts = [f"@{k}:{v}" for k, v in attributes.items()]
        return f"{tag} {' '.join(attr_parts)}"
    return tag

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
    lang_def = parsed_header.get("CATALOG", {}).get("LANGUAGE @default:true", parsed_header.get("CATALOG", {}).get("LANGUAGE", ''))
    logger.info(f"Výchozí jazyk: {lang_def}")
    logger.debug("Header data: %s", parsed_header)
    flat_header = flatten_dict(parsed_header)
    save_to_csv(f"{file_name}_head", [flat_header], logger)

# Parse Products
def parse_BME_products(root, file_name, logger):
    all_product_entries, all_mime_entries, all_keyword_entries = [], [], []

    logger.info("Analýza PRODUCT dat.")

    for product in root.iterfind(".//PRODUCT"):
        product_data = parse_element(product, logger)
        supplier_pid = next((product_data[key] for key in product_data if key.startswith("SUPPLIER_PID")), "N/A")
        logger.debug(f"Zpracovávám produkt:{supplier_pid}")
        # Parse product details
        product_entries = parse_BME_product(product_data, logger)
        for entry in product_entries:
            entry["SUPPLIER_PID"] = supplier_pid
            all_product_entries.append(entry)

        # Parse MIME data
        mime_data = parse_BME_mime(product_data, logger)
        for entry in mime_data:
            entry["SUPPLIER_PID"] = supplier_pid
            all_mime_entries.append(entry)

        # Parse Keywords
        keyword_entries = parse_BME_keyword(product_data, logger)
        all_keyword_entries.extend(keyword_entries)

    save_to_csv(f"{file_name}_produkty", all_product_entries, logger)
    save_to_csv(f"{file_name}_soubory", all_mime_entries, logger)
    save_to_csv(f"{file_name}_klicova_slova", all_keyword_entries, logger)
    

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
                logger.debug(f"MIME_CODE nenalezem, hledám v MIME_DESCR ")
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
    # Sanitize new-line in value
    def sanitize_value(value):
        if isinstance(value, str):
            return value.replace('\n', ' ').replace('\r', ' ').strip()
        return value
        
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

    return [{"SUPPLIER_PID": supplier_pid, "keyword_tag": tag, "keyword_value": value}
            for tag, value in product_details.items() if tag.startswith("KEYWORD") and value]
