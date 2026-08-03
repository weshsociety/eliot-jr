# API locale d’Eliot-Jr

Le serveur actif est `voix/api/server.py` et écoute localement sur
`127.0.0.1:5000`.

## Contrat d’honnêteté

- `/api/see` ne prétend plus mémoriser tant qu’aucun registre transactionnel
  n’est branché. Il répond `501` et confirme `memory_written: false`.
- `/api/memory` décrit seulement les racines observables. Il ne revendique
  ni complétude ni audit d’intégrité.
- les erreurs de requête sont retournées en JSON ;
- les horodatages publics sont en UTC explicite ;
- la liste des routes est calculée depuis Flask, sans compteur figé ;
- les requêtes sont limitées à 64 Kio par défaut ;
- les messages de dialogue sont limités à 8 000 caractères par défaut.

Variables d’environnement :

```text
ELIOT_API_MAX_REQUEST_BYTES
ELIOT_API_MAX_MESSAGE_CHARS
ELIOT_WISDOM_PATH
ELIOT_BACKUP_PATH
```

Aucune route de cette phase n’ajoute de mécanisme d’écriture dans les
registres d’Eliot-Jr.

## Dépendance Flask

La version cible est Flask `3.1.3`. L’installation de la dépendance reste une
opération explicite dans l’environnement virtuel ; l’application du code ne
redémarre pas automatiquement le service.
