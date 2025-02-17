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

    save_to_csv(f"{file_name}_products", all_product_entries, logger)
    save_to_csv(f"{file_name}_mime_products", all_mime_entries, logger)
    save_to_csv(f"{file_name}_keyword_products", all_keyword_entries, logger)

# Parse MIME
def parse_BME_mime(data, logger):
    mime_entries = []
    
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
    logger.debug("Falling back to MIME_INFO in main structure.")
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
    
    for tag, value in product_details.items():
        if isinstance(value, list):  # Convert lists to comma-separated strings
            value = ", ".join(map(str, value))
        product_entry[tag] = value

    return [product_entry]

# Parse Keywords
def parse_BME_keyword(product_data, logger):
    supplier_pid = next((product_data[key] for key in product_data if key.startswith("SUPPLIER_PID")), "N/A")
    product_details = product_data.get("PRODUCT_DETAILS", {})

    return [{"SUPPLIER_PID": supplier_pid, "keyword_tag": tag, "keyword_value": value}
            for tag, value in product_details.items() if tag.startswith("KEYWORD") and value]
