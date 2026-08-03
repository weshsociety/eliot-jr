# Stabilisation — phase 1

## Corrections incluses

- suppression de la clé Python dupliquée `direct_observation_marker` ;
- séparation entre déclaration publique et observation directe ;
- passage de la méthode d’extraction à
  `deterministic_surface_rules_v3` ;
- mise en quarantaine des candidats dont le SHA-256 source a changé avant
  l’enrichissement ;
- standardisation du nom `plan_mondial` dans le code et l’état courant ;
- mise à jour de la documentation du connecteur Obsidian ;
- première suite de tests de non-régression.

## Limites conservées

- aucune relation candidate n’est créée ;
- aucun fichier de `core/` n’est modifié ;
- aucune sortie n’est promue automatiquement ;
- les anciennes archives ne sont pas réécrites.

## Commandes de contrôle

```bash
python3 -m py_compile \
  laboratory/extract_claim_candidates.py \
  laboratory/enrich_claim_context.py \
  laboratory/build_obsidian_inventory.py \
  laboratory/query_obsidian.py \
  connectors/obsidian/read_only_client.py

python3 -m unittest discover -s tests -v
```
