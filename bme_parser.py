import xml.etree.ElementTree as ET
import csv

# Recursively parse an XML element, handling deeply nested structures.
def parse_element(element, logger):
    if element is None:
        logger.warning("Element nenalezen (None).")
        return None
    parsed_data = {}
    
    #Remove namespace from tag name.
    def clean_tag(tag):
        return tag.split('}')[-1]
        
    # Create a combined key from tag name and attributes.
    def create_key(tag, attributes):
        key = tag
        if attributes:
            attr_parts = [f"@{attr}:{value}" for attr, value in attributes.items()]
            key += " " + " ".join(attr_parts)
        return key
        
    # Process a single child element.
    def process_child(child):
        tag = clean_tag(child.tag)
        element_attr = child.attrib
        combined_key = create_key(tag, element_attr)
        # Recursively parse child elements
        child_data = parse_element(child, logger) if len(child) > 0 else (child.text.strip() if child.text else None)
        # Handle key existence
        if combined_key in parsed_data:
            # Ensure the existing value is in a list
            if not isinstance(parsed_data[combined_key], list):
                parsed_data[combined_key] = [parsed_data[combined_key]]
            parsed_data[combined_key].append(child_data)
        else:
            parsed_data[combined_key] = child_data
    # Process all children
    for child in element:
        process_child(child)
    return parsed_data


def flatten_dict(d, parent_key="", sep="_"):
    """ Rekurzivně převede vnořený slovník na plochý slovník. """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            for i, item in enumerate(v):
                list_key = f"{new_key}_{i}"
                if isinstance(item, dict):
                    items.extend(flatten_dict(item, list_key, sep=sep).items())
                else:
                    items.append((list_key, item))
        else:
            items.append((new_key, v))
    return dict(items)


def parse_BME_header(root, file_name, logger):
    headers_data = []
    column_order = set()  # Použijeme množinu pro unikátní názvy sloupců

    # Použití iterfind pro efektivnější vyhledání elementu HEADER
    header = next(root.iterfind(".//HEADER"), None)
    if header is not None:
        logger.info("Analýza HEADER dat.")

        # Použití parse_element
        parsed_header = parse_element(header, logger)
        
        # Získání výchozího jazyka katalogu
        lang_def = parsed_header.get("CATALOG", {}).get("LANGUAGE @default:true", '')
        logger.info(f"Výchozí jazyk: {lang_def}")
        
        # Získání jazyka katalogu
        lang = parsed_header.get("CATALOG", {}).get("LANGUAGE", '')
        if not lang_def:
            lang_def = lang
        logger.info(f"Jazyk: {lang}")
        logger.debug("Header data: %s", parsed_header)
        
        # Převedení do plochého slovníku
        flat_header = flatten_dict(parsed_header)

        # Aktualizace pořadí sloupců
        column_order.update(flat_header.keys())

        headers_data.append(flat_header)

        # Zápis do CSV se zachováním pořadí
        with open(f'output/{file_name}_head.csv', "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=sorted(column_order))
            writer.writeheader()
            for row in headers_data:
                writer.writerow({col: row.get(col, "") for col in sorted(column_order)})
    else:
        logger.warning("Nenalezen HEADER v XML souboru.")
        return None


def parse_BME_products(root_element, file_name, logger):
    all_products_data = []
    logger.info("Analýza PRODUCT dat.")
    
    for product in root_element.iterfind(f'.//{"PRODUCT"}'):
        product_data = parse_element(product)
        log_product = next((product_data[key] for key in product_data if key.startswith("SUPPLIER_PID")), 'N/A')
        logger.debug(f"Zpracovávám produkt:{log_product}")
        #parse_to_csv(product_data, file_name)
        #parse_to_csv_mime(product_data, file_name)
        #parse_to_csv_features(product_data, file_name)
        all_products_data.append(product_data)
    
    return all_products_data

def parse_BME_mime(data, file_name, logger):
    # Extract MIME entries from the data structure.
    # <USER_DEFINED_EXTENSIONS>
    #  <UDX.EDXF.MIME_INFO>
    #   <UDX.EDXF.MIME>
    def get_mime_entries(data):
        user_defined_extensions = data.get("USER_DEFINED_EXTENSIONS")
        if user_defined_extensions:
            mime_info = user_defined_extensions.get("UDX.EDXF.MIME_INFO")
            if mime_info:
                mime_entrie = mime_info.get("UDX.EDXF.MIME", [])
                return mime_entrie
        # Fallback to main structure
        logger.debug("Falling back to MIME_INFO in main structure.")
        mime_info = data.get("MIME_INFO")
        if mime_info:
            mime_entrie = mime_info.get("MIME", [])
            return mime_entrie
        return []

    # Ensure MIME entries are returned as a list.
    def ensure_list(entries):
        if isinstance(entries, dict):
            return [entries]
        return entries

    # Extract keys and values starting with the given prefix.
    def extract_variants(entry, prefix):
        return {key: value for key, value in entry.items() if key.startswith(prefix)}
    
    # Write CSV headers if not already written.
    def write_csv_header(writer, headers):
        global mime_header_written
        if not mime_header_written:
            writer.writerow(headers)
            mime_header_written = True

    # Start processing    
    supplier_pid = next((data[key] for key in data if key.startswith("SUPPLIER_PID")), "N/A")
    logger.debug(f"MIME.SUPPLIER_PID:{supplier_pid}")
    
    mime_entries = ensure_list(get_mime_entries(data))
    if not mime_entries:
        logger.warning(f"MIME(soubory) nenalezeny u produktu: {supplier_pid}")
        return
    
    # Check if the file exists and delete it
    output_file = f'output/{file_name}_mime_products.csv'
    # if os.path.exists(output_file):
        # if not mime_header_written:
            # logger.warning(f"File {output_file} already exists.")
            # os.remove(output_file)

    with open(output_file, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        
        for entry in mime_entries:
            # Handle MIME_SOURCE, MIME_DESCR, MIME_PURPOSE, MIME_CODE, etc.
            mime_source_variants = extract_variants(entry, "MIME_SOURCE") | extract_variants(entry, "UDX.EDXF.MIME_SOURCE")
            mime_descr_variants = extract_variants(entry, "MIME_DESCR") | extract_variants(entry, "UDX.EDXF.MIME_DESIGNATION")
            mime_code = entry.get("MIME_CODE") or entry.get("UDX.EDXF.MIME_CODE", '')
            mime_purpose = entry.get("MIME_PURPOSE", '')  # Only available in main structure
            mime_type = entry.get("MIME_TYPE", '')  # Only available in main structure
            mime_filename = entry.get("UDX.EDXF.MIME_FILENAME", '')  # Only available in USER_DEFINED_EXTENSIONS
            mime_order = entry.get("UDX.EDXF.MIME_ORDER", '')
            # Collect all language variants (or default fields)
            mime_sources = sorted(mime_source_variants.keys())
            mime_descrs = sorted(mime_descr_variants.keys())
            
            # Define CSV headers
            headers = [
                "SUPPLIER_PID", "MIME_CODE",
                *mime_sources,  # All possible MIME_SOURCE variants
                *mime_descrs,   # All possible MIME_DESCR variants
                "MIME_PURPOSE", "MIME_TYPE", "MIME_FILENAME", "MIME_ORDER"
            ]
            write_csv_header(writer, headers)
            row = [
                supplier_pid, mime_code,
                *[mime_source_variants.get(key, '') for key in mime_sources],  # Populate MIME_SOURCE columns
                *[mime_descr_variants.get(key, '') for key in mime_descrs],    # Populate MIME_DESCR columns
                mime_purpose, mime_type, mime_filename, mime_order  # Other fields
            ]
            writer.writerow(row)