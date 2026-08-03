# Schémas d’enquête — Phase 2B

Ces schémas décrivent deux objets intermédiaires stricts :

- `relation_candidate.schema.json` : relation externe sourcée, non validée
  comme vraie ;
- `encounter_packet.schema.json` : paquet préparé après revue humaine pour
  une future rencontre transactionnelle.

## Garanties

- JSON Schema Draft 2020-12 ;
- propriétés supplémentaires refusées ;
- source, lignes et extrait verbatim obligatoires ;
- empreintes SHA-256 obligatoires ;
- état épistémique initial `not_assessed` ;
- causalité initiale `not_established` ;
- acceptation pour rencontre impossible sans confirmation humaine explicite ;
- aucune écriture mémoire, OCTOPUS ou publication autorisée par ces objets.

La validation d’un objet ne l’enregistre nulle part. Le pont transactionnel vers
les registres d’Eliot-Jr appartient à une phase ultérieure.
