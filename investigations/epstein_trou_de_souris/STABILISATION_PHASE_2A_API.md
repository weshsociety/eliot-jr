# Stabilisation Phase 2A — Contrat API

## Périmètre

Cette phase corrige uniquement le serveur Flask public/local. Elle ne branche
aucune nouvelle écriture dans la mémoire ou les registres d’Eliot-Jr.

## Garanties ajoutées

- `/api/see` ne déclare plus une mémorisation inexistante ;
- `/api/memory` ne revendique plus une complétude non auditée ;
- liste et nombre d’endpoints calculés depuis Flask ;
- horodatage UTC explicite ;
- erreurs 400, 404, 405, 413, 415, 422, 501 et 503 en JSON ;
- limites de taille des requêtes et messages ;
- JSON local corrompu converti en indisponibilité contrôlée ;
- statut du backup indisponible contrôlé ;
- tests Flask isolés avec appels au cœur simulés.

## Hors périmètre

- mémorisation via `/api/see` ;
- authentification ou exposition nginx ;
- écriture de relations candidates ;
- modification des registres vivants ;
- prétention d’audit complet de la mémoire.

## Dépendance

`requirements.txt` cible Flask `3.1.3`. Le changement de dépendance et le
redémarrage du service restent explicites et séparés de l’application des
fichiers.
