"""
Gestion du fichier de timestamp de synchronisation.
"""

import json
import logging
import os
from datetime import datetime

from config.config import PathsConfig

logger = logging.getLogger(__name__)


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
        logger.error(f"Le fichier {timestamp_file} n'existe pas", exc_info=True)

    try:
        with open(timestamp_file, "r") as f:
            data = json.load(f)
            timestamp_str = data["lastSuccessFullTime"]
            logger.info(f"Timestamp lu: {timestamp_str}")
            return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f")

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.error(f"Erreur lors du chargement du timestamp : {e}", exc_info=True)
        return datetime.now()


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
