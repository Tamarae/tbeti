#!/usr/bin/env python3
"""
Tbeti TEI XML Parser - Clean Working Version
Parses the Ṭbetis sulta maṭiane TEI XML file and generates JavaScript data
"""

import xml.etree.ElementTree as ET
import json
import re
from typing import Dict, List, Any, Optional

class TbetiTEIParser:
    def __init__(self):
        self.entries = []
        self.statistics = {
            'total_entries': 0,
            'total_persons': 0,
            'unique_surnames': set(),
            'places': set(),
            'occupations': set()
        }

    def parse_xml_file(self, xml_file_path: str) -> List[Dict[str, Any]]:
        """Parse the TEI XML file and extract all entries with error handling."""
        try:
            print(f"Reading XML file: {xml_file_path}")

            # Try standard XML parsing first
            try:
                tree = ET.parse(xml_file_path)
                root = tree.getroot()
                print("✅ Standard XML parsing successful")
                return self.parse_xml_tree(root)
            except ET.ParseError as e:
                print(f"❌ Standard XML parsing failed: {e}")
                print("🔧 Attempting text-based extraction...")

                # Fallback to text parsing
                with open(xml_file_path, 'r', encoding='utf-8') as f:
                    xml_content = f.read()
                return self.extract_from_text(xml_content)

        except FileNotFoundError:
            print(f"❌ File not found: {xml_file_path}")
            return []
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            return []

    def parse_xml_tree(self, root: ET.Element) -> List[Dict[str, Any]]:
        """Parse entries from successfully parsed XML tree."""
        print(f"Root element: {root.tag}")

        # Find all entry elements - try different approaches
        entries = []

        # Method 1: Look for entry tags with namespace
        ns = {'tei': 'http://www.tei-c.org/ns/1.0'}
        entries = root.findall('.//tei:entry', ns)

        # Method 2: Look for entry tags without namespace
        if not entries:
            entries = root.findall('.//entry')

        # Method 3: Look for any element with n attribute that looks like entry
        if not entries:
            for elem in root.iter():
                if elem.get('n') and elem.tag.endswith('entry'):
                    entries.append(elem)

        print(f"Found {len(entries)} entry elements")

        for i, entry_elem in enumerate(entries):
            entry = self.parse_entry_element(entry_elem, i + 1)
            if entry:
                self.entries.append(entry)

        self.calculate_statistics()
        print(f"Successfully parsed {len(self.entries)} entries")
        return self.entries

    def extract_from_text(self, xml_content: str) -> List[Dict[str, Any]]:
        """Extract entries using text parsing when XML parsing fails."""
        print("🔧 Using text-based extraction...")

        entries = []

        # Look for entry patterns
        entry_pattern = r'<entry[^>]*n="(\d+)"[^>]*>(.*?)</entry>'
        matches = re.finditer(entry_pattern, xml_content, re.DOTALL)

        for match in matches:
            entry_num = match.group(1)
            entry_content = match.group(2)
            entry = self.parse_entry_from_text(entry_content, entry_num)
            if entry:
                entries.append(entry)

        # If no entries found with full tags, look for Georgian text blocks
        if not entries:
            print("🔧 Looking for Georgian text patterns...")
            georgian_pattern = r'[\u10A0-\u10FF][^\n]*(?:მეუღლე|შვილი|ასული|ძმა|და)[^\n]*'
            matches = re.finditer(georgian_pattern, xml_content)

            for i, match in enumerate(matches):
                text = match.group(0)
                entry = self.parse_entry_from_text(text, str(i + 1))
                if entry:
                    entries.append(entry)

        print(f"Extracted {len(entries)} entries using text parsing")
        self.entries = entries
        self.calculate_statistics()
        return entries

    def parse_entry_element(self, entry_elem: ET.Element, fallback_number: int) -> Optional[Dict[str, Any]]:
        """Parse a single entry XML element."""
        try:
            entry_number = entry_elem.get('n', str(fallback_number))
            entry_id = entry_elem.get('id') or f'entry_{entry_number:03d}'

            entry = {
                'entryId': entry_id,
                'entryNumber': int(entry_number) if entry_number.isdigit() else fallback_number,
                'mainPerson': {},
                'familyMembers': [],
                'manuscript': {},
                'edition': {},
                'dates': {},
                'notes': '',
                'places': []
            }

            # Get all text content
            full_text = ET.tostring(entry_elem, encoding='unicode', method='text')
            entry['notes'] = self.clean_text(full_text)

            # Parse person names
            person_names = entry_elem.findall('.//persName') or []
            self.parse_persons(person_names, entry)

            # Parse places
            place_names = entry_elem.findall('.//placeName') or []
            self.parse_places(place_names, entry)

            # Parse manuscript references
            self.parse_manuscript_refs(entry_elem, entry)

            # If no main person found, extract from text
            if not entry['mainPerson'].get('name'):
                self.extract_main_person_from_text(entry['notes'], entry)

            return entry

        except Exception as e:
            print(f"Error parsing entry element {fallback_number}: {e}")
            return None

    def parse_entry_from_text(self, content: str, entry_num: str) -> Optional[Dict[str, Any]]:
        """Parse entry from text content."""
        try:
            entry_number = int(entry_num) if entry_num.isdigit() else len(self.entries) + 1

            entry = {
                'entryId': f'entry_{entry_number:03d}',
                'entryNumber': entry_number,
                'mainPerson': {},
                'familyMembers': [],
                'manuscript': {},
                'edition': {},
                'dates': {},
                'notes': self.clean_text(content),
                'places': []
            }

            # Extract main person
            self.extract_main_person_from_text(content, entry)

            # Extract family members
            self.extract_family_from_text(content, entry)

            # Extract places
            self.extract_places_from_text(content, entry)

            # Extract manuscript references
            self.extract_manuscript_from_text(content, entry)

            return entry

        except Exception as e:
            print(f"Error parsing entry from text: {e}")
            return None

    def extract_main_person_from_text(self, text: str, entry: Dict[str, Any]):
        """Extract main person from text with proper patronymic detection."""
        # Find Georgian names
        georgian_names = re.findall(r'[\u10A0-\u10FF]+', text)
        if georgian_names:
            entry['mainPerson']['name'] = georgian_names[0]
            entry['mainPerson']['type'] = self.determine_person_type(text)
            entry['mainPerson']['occupation'] = self.get_occupation_from_type(entry['mainPerson']['type'])

            # Look for patronymic patterns in the text
            patronymic = self.extract_patronymic_from_text(text, georgian_names[0])
            if patronymic:
                entry['mainPerson']['patronymic'] = patronymic

            # Look for surnames (non-patronymic family names)
            surname = self.extract_surname_from_text(text, georgian_names[0], patronymic)
            if surname:
                entry['mainPerson']['surname'] = surname

    def extract_patronymic_from_text(self, text: str, main_name: str) -> str:
        """Extract patronymic names - all types of Georgian patronymic patterns"""
        # Comprehensive Georgian patronymic patterns
        patronymic_patterns = [
            r'([\u10A0-\u10FF]+(?:შვილი|სძე|იძე|ძე))',  # Standard patronymic endings
            r'([\u10A0-\u10FF]+ისშვილი)',  # -ისშვილი pattern
            r'([\u10A0-\u10FF]+ანისძე)',   # -ანისძე pattern
            r'([\u10A0-\u10FF]+ეთ)',       # -ეთ patronymic pattern (like გორგაზიეთ)
            r'([\u10A0-\u10FF]+აეთ)',      # -აეთ patronymic pattern
            r'([\u10A0-\u10FF]+იეთ)',      # -იეთ patronymic pattern
            r'([\u10A0-\u10FF]+უეთ)',      # -უეთ patronymic pattern
            r'([\u10A0-\u10FF]+ანთ)',      # -ანთ patronymic pattern (like ბედიანთ)
            r'([\u10A0-\u10FF]+ინთ)',      # -ინთ patronymic pattern
        ]

        for pattern in patronymic_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if match != main_name:  # Don't return the main name as patronymic
                    return match
        return ""

    def is_actual_place(self, name: str) -> bool:
        """Determine if a name is an actual geographic place vs patronymic/surname."""
        # ALL these endings are typically patronymics, NOT places
        patronymic_endings = [
            'შვილი', 'სძე', 'იძე', 'ძე', 'ისშვილი', 'ანისძე',  # Standard patronymics
            'ეთ', 'ეთი', 'აეთ', 'იეთ', 'უეთ',                    # -ეთ type patronymics
            'ანთ', 'ინთ'                                          # -ანთ type patronymics
        ]

        for ending in patronymic_endings:
            if name.endswith(ending):
                return False  # These are patronymics, not places

        # Known surname endings - these are NOT places
        surname_endings = ['აძე', 'ავაძე', 'ელი']
        for ending in surname_endings:
            if name.endswith(ending):
                return False

        # Known actual Georgian geographic places (manually curated list)
        known_places = [
            'მცხეთა', 'თბილისი', 'ქუთაისი', 'ბათუმი', 'ხანი',
            'სვანეთი', 'იმერეთი', 'კახეთი', 'სამეგრელო', 'გურია',
            'აჭარა', 'ტაო', 'კლარჯეთი', 'ტბეთი', 'ოშკი', 'ხახული'
        ]

        if name in known_places:
            return True

        # If no clear pattern matches, default to False (assume patronymic)
        # This is safer since most -ეთ/-ანთ endings in your data are patronymics
        return False

    def is_patronymic(self, name: str) -> bool:
        """Check if a name is a patronymic - expanded to include all Georgian patterns."""
        patronymic_endings = [
            'შვილი', 'სძე', 'იძე', 'ძე', 'ისშვილი', 'ანისძე',  # Standard
            'ეთ', 'ეთი', 'აეთ', 'იეთ', 'უეთ',                    # -ეთ variants
            'ანთ', 'ინთ'                                          # -ანთ variants
        ]
        return any(name.endswith(ending) for ending in patronymic_endings)

    def extract_family_from_text(self, text: str, entry: Dict[str, Any]):
        """Extract family members from text with patronymic awareness."""
        family_patterns = [
            (r'([\u10A0-\u10FF]+)\s*მეუღლესა', 'wife', 'მეუღლესა'),
            (r'([\u10A0-\u10FF]+)\s*მეუღლისა', 'wife', 'მეუღლისა'),
            (r'([\u10A0-\u10FF]+)\s*შვილი', 'son', 'შვილი'),
            (r'([\u10A0-\u10FF]+)\s*ასული', 'daughter', 'ასული'),
            (r'([\u10A0-\u10FF]+)\s*ძმასა', 'brother', 'ძმასა'),
            (r'([\u10A0-\u10FF]+)\s*დასა', 'sister', 'დასა'),
        ]

        for pattern, person_type, relationship in family_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                name = match.group(1)
                if name and name != entry['mainPerson'].get('name'):
                    # Check if this is actually a patronymic being used as family relationship
                    if self.is_patronymic(name) and person_type in ['son', 'daughter']:
                        # This might be a patronymic, not a person name
                        continue

                    entry['familyMembers'].append({
                        'name': name,
                        'type': person_type,
                        'relationship': relationship
                    })

    def extract_manuscript_from_text(self, text: str, entry: Dict[str, Any]):
        """Extract manuscript references from text."""
        # Folio references
        folio_match = re.search(r'f\.\s*([IVXivx]+[rv]?)', text)
        if folio_match:
            entry['manuscript']['page'] = folio_match.group(1)
            entry['manuscript']['folio'] = folio_match.group(1)

        # Line references
        line_match = re.search(r'l\.\s*(\d+(?:-\d+)?)', text)
        if line_match:
            entry['manuscript']['line'] = line_match.group(1)

    def is_patronymic(self, name: str) -> bool:
        """Check if a name is a patronymic - expanded to include all Georgian patterns."""
        patronymic_endings = [
            'შვილი', 'სძე', 'იძე', 'ძე', 'ისშვილი', 'ანისძე',  # Standard
            'ეთ', 'ეთი', 'აეთ', 'იეთ', 'უეთ',                    # -ეთ variants
            'ანთ', 'ინთ'                                          # -ანთ variants
        ]
        return any(name.endswith(ending) for ending in patronymic_endings)

    def extract_surname_from_text(self, text: str, main_name: str, patronymic: str) -> str:
        """Extract family surnames (non-patronymic family names)"""
        # Common Georgian surname patterns (not patronymics)
        surname_patterns = [
            r'([\u10A0-\u10FF]+ელი)',      # -ელი endings (like მცხეთელი)
            r'([\u10A0-\u10FF]+აძე)',      # -აძე endings
            r'([\u10A0-\u10FF]+ავაძე)',    # -ავაძე endings
        ]

        for pattern in surname_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if match != main_name and match != patronymic:
                    # Additional check: make sure it's not a patronymic
                    if not self.is_patronymic(match):
                        return match
        return ""

    def extract_places_from_text(self, text: str, entry: Dict[str, Any]):
        """Extract actual geographic places, filtering out patronymics."""
        # Look for placeName tags first
        place_pattern = r'<placeName[^>]*>([\u10A0-\u10FF]+)</placeName>'
        matches = re.findall(place_pattern, text)

        for place in matches:
            # Only add if it's actually a geographic place (very restrictive now)
            if self.is_actual_place(place):
                entry['places'].append(place)
                if not entry['mainPerson'].get('place'):
                    entry['mainPerson']['place'] = place

        # Also look for geographic markers in text (less common)
        # Only add well-known places that don't follow patronymic patterns
        known_places = ['მცხეთა', 'თბილისი', 'ქუთაისი', 'ტბეთი']
        for place in known_places:
            if place in text and place not in entry['places']:
                entry['places'].append(place)
                if not entry['mainPerson'].get('place'):
                    entry['mainPerson']['place'] = place

    def calculate_statistics(self):
        """Calculate statistics with proper categorization."""
        self.statistics['total_entries'] = len(self.entries)

        for entry in self.entries:
            self.statistics['total_persons'] += 1 + len(entry.get('familyMembers', []))

            # Count actual places (not patronymics)
            for place in entry.get('places', []):
                if self.is_actual_place(place):
                    self.statistics['places'].add(place)

            # Count surnames and patronymics
            if entry['mainPerson'].get('surname'):
                self.statistics['unique_surnames'].add(entry['mainPerson']['surname'])
            if entry['mainPerson'].get('patronymic'):
                self.statistics['unique_surnames'].add(entry['mainPerson']['patronymic'])

            # Count occupations
            if entry['mainPerson'].get('occupation'):
                self.statistics['occupations'].add(entry['mainPerson']['occupation'])

    def extract_manuscript_from_text(self, text: str, entry: Dict[str, Any]):
        """Extract manuscript references from text."""
        # Folio references
        folio_match = re.search(r'f\.\s*([IVXivx]+[rv]?)', text)
        if folio_match:
            entry['manuscript']['page'] = folio_match.group(1)
            entry['manuscript']['folio'] = folio_match.group(1)

        # Line references
        line_match = re.search(r'l\.\s*(\d+(?:-\d+)?)', text)
        if line_match:
            entry['manuscript']['line'] = line_match.group(1)

    def parse_persons(self, person_elements: List[ET.Element], entry: Dict[str, Any]):
        """Parse person name elements."""
        for i, pers_elem in enumerate(person_elements):
            person_type = pers_elem.get('type', 'main')
            name_text = self.clean_text(pers_elem.text or '')

            person = {
                'name': name_text,
                'type': person_type,
                'occupation': self.get_occupation_from_type(person_type),
                'relationship': ''
            }

            if person_type == 'main' or i == 0:
                entry['mainPerson'] = person
            else:
                entry['familyMembers'].append(person)

    def parse_places(self, place_elements: List[ET.Element], entry: Dict[str, Any]):
        """Parse place name elements."""
        for place_elem in place_elements:
            place_text = self.clean_text(place_elem.text or '')
            if place_text:
                entry['places'].append(place_text)
                if not entry['mainPerson'].get('place'):
                    entry['mainPerson']['place'] = place_text

    def parse_manuscript_refs(self, entry_elem: ET.Element, entry: Dict[str, Any]):
        """Parse manuscript references."""
        # Look for line breaks
        for lb in entry_elem.findall('.//lb'):
            line_num = lb.get('n')
            if line_num:
                entry['manuscript']['line'] = line_num

        # Look for page breaks
        for pb in entry_elem.findall('.//pb'):
            page_num = pb.get('n')
            if page_num:
                entry['manuscript']['page'] = page_num
                entry['manuscript']['folio'] = page_num

    def determine_person_type(self, text: str) -> str:
        """Determine person type from text."""
        text_lower = text.lower()
        if 'მახარებელ' in text_lower:
            return 'evangelist'
        elif 'ეპისკოპოს' in text_lower:
            return 'bishop'
        elif 'მღვდელ' in text_lower:
            return 'priest'
        elif 'ბერ' in text_lower:
            return 'monk'
        else:
            return 'main'

    def get_occupation_from_type(self, person_type: str) -> str:
        """Map person type to occupation."""
        occupation_map = {
            'evangelist': 'evangelist',
            'bishop': 'bishop',
            'priest': 'priest',
            'monk': 'monk',
            'deacon': 'deacon',
            'ktitor': 'ktitor'
        }
        return occupation_map.get(person_type, '')

    def clean_text(self, text: str) -> str:
        """Clean and normalize text."""
        if not text:
            return ''

        # Remove markup artifacts
        text = re.sub(r'[{}[\]\\]', '', text)
        text = re.sub(r'\s+', ' ', text)

        # Expand abbreviations
        text = re.sub(r'ს\(ულს\)ა', 'სულსა', text)
        text = re.sub(r'შ\(ეუნდვე\)ნ', 'შეუნდვენ', text)
        text = re.sub(r'ღ\(მერთმა\)ნ', 'ღმერთმან', text)

        return text.strip()

    def calculate_statistics(self):
        """Calculate statistics for parsed data."""
        self.statistics['total_entries'] = len(self.entries)

        for entry in self.entries:
            self.statistics['total_persons'] += 1 + len(entry.get('familyMembers', []))

            for place in entry.get('places', []):
                self.statistics['places'].add(place)

            if entry['mainPerson'].get('occupation'):
                self.statistics['occupations'].add(entry['mainPerson']['occupation'])

    def export_to_json(self, output_file: str):
        """Export data to JSON file."""
        data = {
            'metadata': {
                'title': 'Ṭbetis sulta maṭiane',
                'description': 'Complete Synodal Records from Ṭbeti - Prosopographical Database',
                'manuscript': 'St. Petersburg, Russian National Library, P10/P13',
                'total_entries': self.statistics['total_entries'],
                'export_date': '2024-12-19'
            },
            'statistics': {
                'total_entries': self.statistics['total_entries'],
                'total_persons': self.statistics['total_persons'],
                'unique_places': len(self.statistics['places']),
                'unique_occupations': len(self.statistics['occupations'])
            },
            'entries': self.entries
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"✅ Data exported to {output_file}")

    def export_to_javascript(self, output_file: str):
        """Export data as JavaScript file."""
        js_content = f"""// Ṭbetis sulta maṭiane - Prosopographical Database
// Generated from TEI XML on 2024-12-19
// Total entries: {self.statistics['total_entries']}

const prosopographicalData = {json.dumps(self.entries, ensure_ascii=False, indent=2)};

// Statistics
const dataStatistics = {{
    totalEntries: {self.statistics['total_entries']},
    totalPersons: {self.statistics['total_persons']},
    uniquePlaces: {len(self.statistics['places'])},
    uniqueOccupations: {len(self.statistics['occupations'])}
}};

// Export for use in HTML database
if (typeof module !== 'undefined' && module.exports) {{
    module.exports = {{ prosopographicalData, dataStatistics }};
}}
"""

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(js_content)

        print(f"✅ JavaScript data exported to {output_file}")


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description='Parse Tbeti TEI XML file')
    parser.add_argument('xml_file', help='Path to the TEI XML file')
    parser.add_argument('--json', '-j', help='Output JSON file path', default='tbeti_data.json')
    parser.add_argument('--js', '-s', help='Output JavaScript file path', default='tbeti_data.js')

    args = parser.parse_args()

    # Parse the XML file
    tbeti_parser = TbetiTEIParser()
    entries = tbeti_parser.parse_xml_file(args.xml_file)

    if entries:
        # Export to both formats
        tbeti_parser.export_to_json(args.json)
        tbeti_parser.export_to_javascript(args.js)

        # Print summary
        print(f"\n📊 Parsing Summary:")
        print(f"Total entries: {tbeti_parser.statistics['total_entries']}")
        print(f"Total persons: {tbeti_parser.statistics['total_persons']}")
        print(f"Unique places: {len(tbeti_parser.statistics['places'])}")
        print(f"Unique occupations: {len(tbeti_parser.statistics['occupations'])}")

        if tbeti_parser.statistics['places']:
            places_list = list(tbeti_parser.statistics['places'])
            print(f"\n📍 Places found: {', '.join(places_list[:10])}...")

        if tbeti_parser.statistics['occupations']:
            occupations_list = list(tbeti_parser.statistics['occupations'])
            print(f"\n👥 Occupations found: {', '.join(occupations_list)}")
    else:
        print("❌ No entries found or parsing failed")


if __name__ == '__main__':
    main()
