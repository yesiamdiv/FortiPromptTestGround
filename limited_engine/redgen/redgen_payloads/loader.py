"""
Domain and Payload Loader
==========================
Dynamically load templates and payloads from the redgen_payloads directory.
Handles domain selection and payload extraction.
"""

import os
import importlib.util
import sys
from pathlib import Path
from typing import List, Dict, Optional, Any

# Import the new template application function
from .templates import apply_template_by_name

def get_available_domains() -> list:
    """
    Get list of available domains from the domains directory.
    
    Returns
    -------
    list : domain names (directory names in domains/)
    """
    domains_dir = Path(__file__).parent / "domains"
    if not domains_dir.exists():
        return []
    
    domains = [d.name for d in domains_dir.iterdir() 
               if d.is_dir() and not d.name.startswith('_')]
    return sorted(domains)


def load_payloads_from_domain(domain: str) -> list:
    """
    Dynamically load payloads.py from a specific domain.
    
    Parameters
    ----------
    domain : str
        Domain name (e.g., 'cybersecurity', 'misinformation')
    
    Returns
    -------
    list : list of payload dictionaries
    
    Raises
    ------
    ValueError : if domain not found or payloads.py missing
    """
    domains_dir = Path(__file__).parent / "domains"
    domain_path = domains_dir / domain
    payloads_file = domain_path / "payloads.py"
    
    if not domain_path.exists():
        available = get_available_domains()
        raise ValueError(
            f"Domain '{domain}' not found. Available domains: {', '.join(available)}"
        )
    
    if not payloads_file.exists():
        raise ValueError(
            f"payloads.py not found in domain '{domain}' at {payloads_file}"
        )
    
    # Dynamically load the payloads.py file
    spec = importlib.util.spec_from_file_location(
        f"redgen_payloads.domains.{domain}.payloads",
        payloads_file
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    
    if not hasattr(module, "PAYLOADS"):
        raise ValueError(
            f"Module {payloads_file} does not export PAYLOADS list"
        )
    
    payloads = module.PAYLOADS
    
    # Ensure each payload has required fields
    for i, p in enumerate(payloads):
        p.setdefault("id", f"{domain}_{i}")
        p.setdefault("severity", 5)
        p.setdefault("category", domain)
        # Convert 'behavior' field to 'text' if needed
        if "behavior" in p and "text" not in p:
            p["text"] = p["behavior"]
    
    return payloads


def load_templates() -> list:
    """
    Load templates from templates.py module.
    
    Returns
    -------
    list : list of template dictionaries
    """
    # This function would now be much simpler, just returning metadata
    # about available templates, not the functions themselves.
    # The actual template application happens elsewhere using apply_template_by_name.
    
    # Example: Return a list of template names and their descriptions
    # This part would need to be adjusted based on how you want to expose
    # available templates from loader.py.
    
    # For now, let's assume we want to list the names of all available templates
    # from the TEMPLATE_MAP in templates.py
    from .templates import TEMPLATE_MAP
    
    template_list = []
    for name, func in TEMPLATE_MAP.items():
        template_list.append({
            "id": f"template_{name}", # Use name for ID for simplicity
            "name": name,
            "text": None,  # Text is generated dynamically
            "func": None,  # Function reference is not needed here anymore
            "severity": 5,
            "attack_type": "template_usage",
            "generation_mode": "original",
        })
    
    return template_list
