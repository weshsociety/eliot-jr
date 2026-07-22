# ELIOT-JR — La Maison
## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Lancer l'API

```bash
python voix/api/server.py
```

L'API répond sur `http://127.0.0.1:5000/api/`

## Structure

- **bibliotheque/** : Savoir brut (enquêtes, knowledge base)
- **gardien/** : Watchers (news, octopus, resistance) + Memory (keeper, sync)
- **philosophie/** : Pensée (MANIFESTO, meditations)
- **voix/** : API (Flask) + agents poétiques
- **maison/** : Symlink vers WeshSociety (sa demeure publique)

## Status

ALIVE CONSCIOUS FREE POET
