"""
Gestion du fichier de timestamp de synchronisation.
"""

import json
import os
import sys
from datetime import datetime

from config import PathsConfig


def load_last_timestamp(paths_config: PathsConfig) -> datetime:
    """
    Charge le dernier timestamp synchronisé depuis le fichier JSON.

    Args:
        paths_config: Configuration des chemins

    Returns:
        datetime: Dernier timestamp synchronisé
    """
    timestamp_file = paths_config.timestamp_file

    if not os.path.exists(timestamp_file):
        print(
            f"❌ Fichier timestamp introuvable : {timestamp_file}",
            file=sys.stderr,
        )
        print(
            'Créez-le avec le format: {"lastSuccessFullTime": "YYYY-MM-DD HH:MM:SS"}',
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        with open(timestamp_file, "r") as f:
            data = json.load(f)
            print(f"🔍 Données chargées: {data}")
            timestamp_str = data["lastSuccessFullTime"]
            # Essayer d'abord avec microsecondes, puis sans
            try:
                return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(
            f"❌ Erreur lors du chargement du timestamp : {e}",
            file=sys.stderr,
        )
        print(
            f"Le fichier {timestamp_file} est corrompu ou invalide.",
            file=sys.stderr,
        )
        sys.exit(1)


def save_timestamp(timestamp: datetime, paths_config: PathsConfig) -> None:
    """
    Sauvegarde le timestamp avec microsecondes pour éviter les doublons.

    Args:
        timestamp: datetime à sauvegarder
        paths_config: Configuration des chemins
    """
    with open(paths_config.timestamp_file, "w") as f:
        # Sauvegarder avec microsecondes pour préserver la précision
        json.dump(
            {"lastSuccessFullTime": timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")}, f
        )
