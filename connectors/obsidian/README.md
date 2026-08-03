# Connecteur Obsidian

État : opérationnel en lecture seule.

Eliot-Jr accède au coffre `plan_mondial` par l’API locale REST
d’Obsidian. Le coffre n’est pas monté comme répertoire sur le VPS.

## Garanties actuelles

- connexion authentifiée par clé conservée hors du dépôt ;
- commandes exposées : `status`, `list`, `read` ;
- périmètre limité aux répertoires de l’enquête Epstein ;
- aucune commande d’écriture, de suppression ou de renommage ;
- chemins relatifs et sorties de la liste blanche refusés.

## Vérification

```bash
python3 connectors/obsidian/read_only_client.py status
python3 connectors/obsidian/read_only_client.py list
python3 connectors/obsidian/read_only_client.py read \
  "000_synthèse/POINT_DE_BASCULE.md"
```

## TLS

Le service écoute localement sur `127.0.0.1`. Tant que
`ELIOT_OBSIDIAN_CA_FILE` n’est pas défini, le certificat auto-signé
d’Obsidian n’est pas vérifié. Cette tolérance est temporaire et doit
être remplacée par une autorité de certification locale explicitement
installée.

Aucune écriture automatique dans Obsidian n’est autorisée.
