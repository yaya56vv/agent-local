"""Outils reseau communs : reconnaitre une adresse locale ou privee.

Une simple visite d'une adresse locale peut declencher une action (ex. un webhook n8n) :
la lecture de page et le navigateur de l'agent n'y vont donc jamais.
"""
import ipaddress
import socket
from urllib.parse import urlparse


def adresse_locale(adresse):
    """Vrai si l'adresse vise la machine elle-meme ou le reseau prive. Un nom introuvable renvoie Faux :
    la visite echouera alors d'elle-meme."""
    hote = urlparse(adresse).hostname
    if not hote:
        return True
    try:
        ips = {info[4][0] for info in socket.getaddrinfo(hote, None)}
    except socket.gaierror:
        return False
    for ip in ips:
        a = ipaddress.ip_address(ip.split("%")[0])
        if a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_unspecified:
            return True
    return False
