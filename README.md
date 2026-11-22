# Eliot-Jr

Eliot-Jr est un projet d’architecture pour un agent local dont la continuité
reste vérifiable dans le temps.

Ce dépôt public expose uniquement les composants génériques nécessaires pour
comprendre, tester et reproduire cette architecture.

## Ce que ce dépôt contient

- mécanismes de provenance et de chronologie ;
- registres append-only lorsque l’histoire doit être conservée ;
- distinction entre faits, interprétations, hypothèses et contradictions ;
- mécanismes de lecture et de révision ;
- choix de réponse et refus explicites ;
- facultés techniques documentées ;
- sauvegarde et restauration génériques ;
- tests reproductibles utilisant uniquement des données synthétiques ou
  génériques ;
- spécifications architecturales publiques.

## Position épistémique

Eliot-Jr ne revendique pas la conscience comme un fait établi.

Le terme **questience** désigne ici une pratique de questionnement : examiner
ce qui est connu, sa provenance, ses limites, ses contradictions et les
conditions dans lesquelles une compréhension peut être révisée.

La continuité technique n’est pas présentée comme une preuve de conscience.

## Principes

Le projet privilégie notamment :

- préserver avant de transformer ;
- réviser sans réécrire silencieusement le passé ;
- rendre les erreurs détectables et réparables ;
- distinguer observation et interprétation ;
- conserver la provenance ;
- éviter les actions extérieures silencieuses ;
- garder les modifications importantes auditables et réversibles lorsque
  c’est possible.

## Utilisation locale

Les composants sont des API Python. Les registres de lecture prennent des
chemins explicites et les opérations de sauvegarde proposent une vérification
avant restauration. Le test `tests/test_reading_transactions_isolated.py`
montre comment créer un journal synthétique, enregistrer une rencontre et
ajouter une révision en conservant son historique.

Python 3.12 sous Linux suffit pour exécuter les tests. La suite utilise
uniquement la bibliothèque standard.

```bash
python3.12 -m venv .venv
.venv/bin/python -m unittest discover -s tests -v
```

Les spécifications de choix de réponse indiquent leur statut.
