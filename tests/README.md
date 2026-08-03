# Tests de stabilisation

La première suite utilise uniquement `unittest`, inclus dans Python. Elle est
aussi découvrable par `pytest` si celui-ci est installé ultérieurement.

```bash
python3 -m unittest discover -s tests -v
```

Elle couvre actuellement :

- distinction entre attribution publique et observation directe ;
- conservation des questions et négations ;
- quarantaine d’une source modifiée avant enrichissement ;
- absence de création de relation et de modification déclarée du cœur ;
- liste blanche et normalisation des chemins Obsidian.
