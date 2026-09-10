import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class EntityTag(BaseModel):
    """
    Represents an entity tag for a blockchain address, indicating ownership,
    category, and risk profile (e.g. OFAC sanctioned).
    
    Fields:
    - entity_name: Name of the entity (e.g. 'Binance')
    - entity_type: The category of the entity ('exchange', 'mixer', 'sanctioned', etc.)
    - source: Origin of the tag ('manual_curated', 'ofac_sdn', etc.)
    - confidence: Confidence score of the tag (0.0 - 1.0)
    - chain: The blockchain network ('bitcoin', 'ethereum', 'multi', etc.)
    - address: The blockchain address associated with the tag
    - source_url: URL reference for the tag source
    - is_sanctioned: Flag indicating if the entity is OFAC sanctioned
    - metadata: Additional metadata related to the tag
    """
    entity_name: str
    entity_type: str
    source: str
    confidence: float
    chain: str
    address: str
    source_url: Optional[str] = None
    is_sanctioned: bool = False
    metadata: Optional[Dict[str, Any]] = None


class KnowledgeBase:
    """
    The VASP TAG DATABASE for VajraTrace blockchain forensics.
    It loads known exchange/entity tags from curated JSON files and OFAC sanctions data.
    """
    
    def __init__(self) -> None:
        """
        Initializes an empty knowledge base.
        """
        self._tags: Dict[str, EntityTag] = {}
        self._loaded: bool = False

    def load(self, tags_dir: Union[str, Path, None] = None, ofac_dir: Union[str, Path, None] = None) -> None:
        """
        Loads tags from curated exchange lists and OFAC sanctions lists.
        
        Args:
            tags_dir: Path to directory containing curated exchange/entity JSON tags.
            ofac_dir: Path to directory containing OFAC sanctioned address lists.
        """
        # Resolve default paths relative to this file's location
        # knowledge_base.py -> attribution -> services -> app -> api -> apps -> vajratrace
        project_root = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
        
        if tags_dir is None:
            tags_dir = project_root / 'data' / 'tags'
        else:
            tags_dir = Path(tags_dir)
            
        if ofac_dir is None:
            ofac_dir = project_root / 'data' / 'ofac'
        else:
            ofac_dir = Path(ofac_dir)
            
        logger.info(f"Loading knowledge base from tags_dir={tags_dir}, ofac_dir={ofac_dir}")
        
        self._load_exchange_tags(tags_dir)
        self._load_ofac_sanctions(ofac_dir)
        
        self._loaded = True
        logger.info(f"Knowledge Base loaded successfully. Total tags: {len(self._tags)}")

    def _load_exchange_tags(self, tags_dir: Path) -> None:
        """Loads curated exchange/entity tags from JSON files in the specified directory.
        
        Supports three sections in the JSON files:
        - ``exchanges``: Known exchange hot/cold wallets
        - ``known_dex_routers``: Known DeFi protocol router contracts
        - ``known_mixers``: Known mixing service addresses
        
        Args:
            tags_dir: The directory containing .json tag files.
        """
        if not tags_dir.exists():
            logger.warning(f"Tags directory not found: {tags_dir}. Skipping exchange tags loading.")
            return

        for json_file in tags_dir.glob('*.json'):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Load exchange addresses
                for exchange in data.get("exchanges", []):
                    entity_name = exchange.get("entity_name", "Unknown")
                    entity_type = exchange.get("entity_type", "exchange")
                    
                    for addr_info in exchange.get("addresses", []):
                        address_val = addr_info.get("address", "").strip()
                        if not address_val:
                            continue
                            
                        tag = EntityTag(
                            entity_name=entity_name,
                            entity_type=entity_type,
                            source='manual_curated',
                            confidence=0.95,
                            chain=addr_info.get("chain", "multi"),
                            address=address_val,
                            source_url=addr_info.get("source_url"),
                            is_sanctioned=False,
                            metadata={"label": addr_info.get("label", "")}
                        )
                        self._tags[address_val.lower()] = tag
                
                # Load known DEX routers
                for dex in data.get("known_dex_routers", []):
                    entity_name = dex.get("entity_name", "Unknown DEX")
                    for addr_info in dex.get("addresses", []):
                        address_val = addr_info.get("address", "").strip()
                        if not address_val:
                            continue
                        tag = EntityTag(
                            entity_name=entity_name,
                            entity_type="defi",
                            source='manual_curated',
                            confidence=0.95,
                            chain=addr_info.get("chain", "ethereum"),
                            address=address_val,
                            source_url=addr_info.get("source_url"),
                            is_sanctioned=False,
                            metadata={"label": addr_info.get("label", "")}
                        )
                        self._tags[address_val.lower()] = tag
                
                # Load known mixers
                for mixer in data.get("known_mixers", []):
                    entity_name = mixer.get("entity_name", "Unknown Mixer")
                    for addr_info in mixer.get("addresses", []):
                        address_val = addr_info.get("address", "").strip()
                        if not address_val:
                            continue
                        tag = EntityTag(
                            entity_name=entity_name,
                            entity_type="mixer",
                            source='manual_curated',
                            confidence=0.95,
                            chain=addr_info.get("chain", "ethereum"),
                            address=address_val,
                            source_url=addr_info.get("source_url"),
                            is_sanctioned=False,
                            metadata={"label": addr_info.get("label", "")}
                        )
                        self._tags[address_val.lower()] = tag
                        
            except Exception as e:
                logger.error(f"Failed to load exchange tags from {json_file}: {e}")

    def _load_ofac_sanctions(self, ofac_dir: Path) -> None:
        """
        Loads OFAC sanctioned addresses from .txt and .xml files in the specified directory.
        Uses iterparse for XML files to ensure memory efficiency with large files.
        
        Args:
            ofac_dir: The directory containing OFAC sanction data.
        """
        if not ofac_dir.exists():
            logger.warning(f"OFAC directory not found: {ofac_dir}. Skipping OFAC sanctions loading.")
            return

        # Load from .txt files (sanctioned_addresses_*.txt)
        for txt_file in ofac_dir.glob('sanctioned_addresses_*.txt'):
            try:
                with open(txt_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        # Skip comments and empty lines
                        if not line or line.startswith('#'):
                            continue
                            
                        # Assuming each line is an address
                        address_val = line
                        tag = EntityTag(
                            entity_name='OFAC Sanctioned Entity',
                            entity_type='sanctioned',
                            source='ofac_sdn',
                            confidence=1.0,
                            chain='multi',
                            address=address_val,
                            is_sanctioned=True
                        )
                        self._tags[address_val.lower()] = tag
            except Exception as e:
                logger.error(f"Failed to load OFAC sanctions from {txt_file}: {e}")
                
        # Load from advanced XML if present (e.g. sdn_advanced.xml)
        for xml_file in ofac_dir.glob('sdn_advanced*.xml'):
            try:
                # Using iterparse for memory efficiency on large XML files (e.g. 126MB)
                context = ET.iterparse(xml_file, events=('end',))
                
                # OFAC SDN advanced XML typically uses namespaces, but we can search for the local tag name
                for event, elem in context:
                    # Strip namespace for tag comparison, if any: '{http://...}Digital_Currency_Address'
                    tag_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                    
                    if tag_name == 'Digital_Currency_Address':
                        address_val = elem.text
                        if address_val:
                            address_val = address_val.strip()
                            tag = EntityTag(
                                entity_name='OFAC Sanctioned Entity',
                                entity_type='sanctioned',
                                source='ofac_sdn',
                                confidence=1.0,
                                chain='multi',  # specific chain could be parsed if available
                                address=address_val,
                                is_sanctioned=True
                            )
                            self._tags[address_val.lower()] = tag
                        
                        # Clear the element from memory to prevent bloat
                        elem.clear()
                        
            except Exception as e:
                logger.error(f"Failed to load OFAC sanctions from {xml_file}: {e}")

    def lookup(self, address: str) -> Optional[EntityTag]:
        """
        Looks up an address in the knowledge base.
        
        Args:
            address: The blockchain address to look up.
            
        Returns:
            The EntityTag if found, otherwise None.
        """
        return self._tags.get(address.lower())

    def lookup_many(self, addresses: List[str]) -> Dict[str, EntityTag]:
        """
        Batch lookup for multiple addresses.
        
        Args:
            addresses: A list of blockchain addresses.
            
        Returns:
            A dictionary mapping the queried address to its EntityTag (if found).
        """
        result = {}
        for address in addresses:
            tag = self.lookup(address)
            if tag is not None:
                result[address] = tag
        return result

    def is_sanctioned(self, address: str) -> bool:
        """
        Quick check if an address is OFAC-sanctioned.
        
        Args:
            address: The blockchain address to check.
            
        Returns:
            True if sanctioned, False otherwise.
        """
        tag = self.lookup(address)
        return tag is not None and tag.is_sanctioned

    def get_all_tags(self) -> Dict[str, EntityTag]:
        """
        Returns a copy of all loaded tags.
        
        Returns:
            A dictionary containing all known tags.
        """
        return self._tags.copy()

    def add_tag(self, tag: EntityTag) -> None:
        """
        Adds a new tag to the knowledge base at runtime.
        Useful for integrating ML-predicted tags or user-submitted tags.
        
        Args:
            tag: The EntityTag to add.
        """
        self._tags[tag.address.lower()] = tag

    @property
    def tag_count(self) -> int:
        """
        Returns the total number of tags loaded in the knowledge base.
        """
        return len(self._tags)

    @property
    def is_loaded(self) -> bool:
        """
        Indicates whether the knowledge base has been loaded.
        """
        return self._loaded

# Module-level singleton
knowledge_base = KnowledgeBase()
