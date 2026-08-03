# Phase 2B — Schémas stricts d’enquête

## Périmètre

Cette phase définit et valide les contrats JSON de `relation_candidate` et de
`encounter_packet`. Elle ne génère aucune relation réelle et n’écrit dans aucun
registre vivant.

## Garanties ajoutées

- JSON Schema Draft 2020-12 ;
- validation des formats de date avec vérificateur explicite ;
- propriétés inconnues refusées ;
- source exacte, lignes et extrait verbatim requis ;
- identifiants et empreintes recalculés de façon déterministe ;
- revue liée à l’empreinte exacte de la candidate ;
- source modifiée interdite pour `accepted_for_encounter` ;
- décision mécanique insuffisante pour accepter une rencontre ;
- paquet de rencontre explicitement non écrivant ;
- tests synthétiques, sans usage des registres vivants.

## Hors périmètre

- extraction automatique de relations ;
- revue réelle par la Guilde ;
- écriture dans `reading_encounter_registry` ;
- apprentissage logique ;
- proposition ou modification OCTOPUS.
