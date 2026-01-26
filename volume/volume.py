"""
Gestion du fichier de timestamp de synchronisation.
"""

import json
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)


def load_last_timestamp(timestamp_file: str) -> datetime:
    """
    Charge le dernier timestamp synchronisé depuis le fichier JSON.

    Args:
        timestamp_file: Chemin vers le fichier de timestamp

    Returns:
        datetime: Dernier timestamp synchronisé
    """

    if not os.path.exists(timestamp_file):
        logger.error(f"Le fichier {timestamp_file} n'existe pas", exc_info=True)

    try:
        with open(timestamp_file, "r") as f:
            data = json.load(f)
            timestamp_str = data["last_successful_time"]
            logger.info(f"Timestamp lu: {timestamp_str}")
            return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f")

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.error(f"Erreur lors du chargement du timestamp : {e}", exc_info=True)
        return datetime.now()


def save_timestamp(timestamp: datetime, timestamp_file: str) -> None:
    """
    Sauvegarde le timestamp avec microsecondes pour éviter les doublons.

    Args:
        timestamp: datetime à sauvegarder
        timestamp_file: Chemin vers le fichier de timestamp
    """
    with open(timestamp_file, "w") as f:
        # Sauvegarder avec microsecondes pour préserver la précision
        json.dump(
            {"last_successful_time": timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")}, f
        )
