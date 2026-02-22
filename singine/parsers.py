"""Parsers for various data formats (CSV, RDF/XML, etc.)."""

import csv
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any, Optional


class CSVDataCategoryParser:
    """Parser for Collibra CSV exports containing Data Categories."""

    def __init__(self, csv_path: Path):
        """Initialize parser with CSV file path."""
        self.csv_path = csv_path

    def parse(self) -> List[Dict[str, str]]:
        """Parse CSV file into list of dictionaries.

        Returns:
            List of row dictionaries with column names as keys
        """
        rows = []

        with open(self.csv_path, 'r', encoding='utf-8') as f:
            # CSV uses semicolon as delimiter
            reader = csv.DictReader(f, delimiter=';')

            for row in reader:
                rows.append(row)

        return rows

    def get_hierarchy(self) -> Dict[str, List[str]]:
        """Build hierarchy map from parent to children.

        Returns:
            Dictionary mapping parent asset IDs to list of child asset IDs
        """
        rows = self.parse()
        hierarchy = {}

        for row in rows:
            parent_id = row.get("[Business Asset] grouped by [Business Asset] > Asset Id")
            child_id = row.get("Asset Id")

            if parent_id:
                if parent_id not in hierarchy:
                    hierarchy[parent_id] = []
                hierarchy[parent_id].append(child_id)

        return hierarchy


class RDFSKOSParser:
    """Parser for RDF/XML files with SKOS concepts."""

    # XML namespaces
    NAMESPACES = {
        'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
        'skos': 'http://www.w3.org/2004/02/skos/core#',
        'dc': 'http://purl.org/dc/elements/1.1/',
        'knowyourai': 'https://github.com/sindoc/knowyourai-framework/blob/main/ontology.owl#',
        'prov': 'http://www.w3.org/ns/prov#',
        'foaf': 'http://xmlns.com/foaf/0.1/',
        'dcterms': 'http://purl.org/dc/terms/'
    }

    def __init__(self, rdf_path: Path):
        """Initialize parser with RDF file path."""
        self.rdf_path = rdf_path
        self.tree = None
        self.root = None

    def parse(self) -> List[Dict[str, Any]]:
        """Parse RDF/XML file into list of concept dictionaries.

        Returns:
            List of SKOS concept dictionaries
        """
        self.tree = ET.parse(self.rdf_path)
        self.root = self.tree.getroot()

        concepts = []

        # Find all skos:Concept elements
        for concept_elem in self.root.findall('.//skos:Concept', self.NAMESPACES):
            concept = self._parse_concept(concept_elem)
            concepts.append(concept)

        return concepts

    def _parse_concept(self, concept_elem: ET.Element) -> Dict[str, Any]:
        """Parse a single SKOS concept element.

        Args:
            concept_elem: XML element for skos:Concept

        Returns:
            Dictionary with concept properties
        """
        concept = {}

        # Get URI (rdf:about attribute)
        concept['uri'] = concept_elem.get(f"{{{self.NAMESPACES['rdf']}}}about", "")

        # Get prefLabel
        pref_label = concept_elem.find('skos:prefLabel', self.NAMESPACES)
        if pref_label is not None:
            concept['prefLabel'] = pref_label.text

        # Get altLabel
        alt_label = concept_elem.find('skos:altLabel', self.NAMESPACES)
        if alt_label is not None:
            concept['altLabel'] = alt_label.text

        # Get description
        description = concept_elem.find('dc:description', self.NAMESPACES)
        if description is not None:
            concept['description'] = description.text

        # Get broader concept
        broader = concept_elem.find('skos:broader', self.NAMESPACES)
        if broader is not None:
            concept['broader'] = broader.get(f"{{{self.NAMESPACES['rdf']}}}resource", "")

        # Get example
        example = concept_elem.find('skos:example', self.NAMESPACES)
        if example is not None:
            concept['example'] = example.text

        # Get note
        note = concept_elem.find('skos:note', self.NAMESPACES)
        if note is not None:
            concept['note'] = note.text

        # Get custom knowyourai properties
        human_role = concept_elem.find('knowyourai:humanRoleLabel', self.NAMESPACES)
        if human_role is not None:
            concept['humanRole'] = human_role.text

        ai_role = concept_elem.find('knowyourai:aiRoleLabel', self.NAMESPACES)
        if ai_role is not None:
            concept['aiRole'] = ai_role.text

        # Get risk profile
        risk_profile_elem = concept_elem.find('knowyourai:RiskProfile', self.NAMESPACES)
        if risk_profile_elem is not None:
            risk_profile = {}

            likelihood = risk_profile_elem.find('knowyourai:likelihood', self.NAMESPACES)
            if likelihood is not None:
                risk_profile['likelihood'] = likelihood.text

            impact = risk_profile_elem.find('knowyourai:impact', self.NAMESPACES)
            if impact is not None:
                risk_profile['impact'] = impact.text

            concept['riskProfile'] = risk_profile

        # Get related resources
        resources = []
        for desc in concept_elem.findall('.//rdf:Description', self.NAMESPACES):
            resource = self._parse_resource(desc)
            if resource:
                resources.append(resource)
        if resources:
            concept['resources'] = resources

        return concept

    def _parse_resource(self, desc_elem: ET.Element) -> Optional[Dict[str, str]]:
        """Parse a resource description (course, book, tool, movie).

        Args:
            desc_elem: rdf:Description element

        Returns:
            Resource dictionary or None
        """
        resource = {}

        # Get resource URI
        resource['uri'] = desc_elem.get(f"{{{self.NAMESPACES['rdf']}}}about", "")

        # Get type
        res_type = desc_elem.find('dcterms:type', self.NAMESPACES)
        if res_type is not None:
            resource['type'] = res_type.text

        # Get title
        title = desc_elem.find('dc:title', self.NAMESPACES)
        if title is not None:
            resource['title'] = title.text

        # Get link
        link = desc_elem.find('foaf:isPrimaryTopicOf', self.NAMESPACES)
        if link is not None:
            resource['link'] = link.get(f"{{{self.NAMESPACES['rdf']}}}resource", "")

        return resource if resource.get('title') else None

    def get_concept_hierarchy(self) -> Dict[str, List[str]]:
        """Build hierarchy from broader/narrower relationships.

        Returns:
            Dictionary mapping parent URIs to child URIs
        """
        concepts = self.parse()
        hierarchy = {}

        for concept in concepts:
            broader_uri = concept.get('broader')
            concept_uri = concept.get('uri')

            if broader_uri:
                if broader_uri not in hierarchy:
                    hierarchy[broader_uri] = []
                hierarchy[broader_uri].append(concept_uri)

        return hierarchy
