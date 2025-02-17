# ETIM_to_CSV (BME-tool)
ETIM_to_CSV (BME-tool) je nástroj v jazyce Python určený k extrakci dat z ETIM (ElectroTechnical Information Model) XML souborů a jejich převodu do formátu CSV.
Tím usnadňuje analýzu a integraci ETIM dat do různých aplikací a pracovních postupů.
Funkce

    Parsování XML: Využívá xml_utils.py pro zpracování ETIM XML souborů.
    Extrakce dat: Používá bme_parser.py k získání relevantních dat z parsovaného XML.
    Převod do CSV: Převede extrahovaná data do formátu CSV pro snadnou integraci.

Požadavky:

    Python 3.x
    Standardní Python knihovny

Použití:

Připravte si ETIM XML soubor: Ujistěte se, že máte ETIM XML soubor, který chcete převést.

Spusťte konverzní skript:

    python main.py cesta/k/vasemu/etim_souboru.xml

Nahraďte cesta/k/vasemu/etim_souboru.xml skutečnou cestou k vašemu ETIM XML souboru.

Výstup:

    Skript vygeneruje CSV a log soubory do adresáře ./output/, který bude obsahovat extrahovaná data.

Přetahování souborů (Drag-and-Drop):

    Pro snadnější použití můžete jednoduše přetáhnout váš ETIM XML soubor přímo na soubor main.py.
    Tímto způsobem se skript automaticky spustí s vybraným souborem jako vstupem.

Ladění:

Pro účely ladění můžete použít volitelný parametr -debug, který poskytne podrobnější výstup pro diagnostiku:

    python main.py -debug cesta/k/vasemu/etim_souboru.xml

Tímto způsobem získáte více informací o průběhu zpracování a případných chybách.
