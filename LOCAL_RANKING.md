# Classement local des offres

`local_rank.py` lit un export SeekSpider JSONL, récupère séquentiellement les descriptions accessibles via le fetcher existant et interroge Ollama en local. Il n'utilise ni PostgreSQL ni API d'IA externe. Les scores sont indicatifs et les extraits doivent être contrôlés dans les annonces. Les offres dont la description est inaccessible sont enregistrées comme échecs dans le fichier JSON voisin.

Exemple sous WSL avec Docker et GPU NVIDIA :

```bash
docker build -t seekspider-local .
docker build -f Dockerfile.local-ranking -t seekspider-run .
docker run -d --gpus all --name seekspider-ollama -p 127.0.0.1:11434:11434 -v seekspider-ollama-models:/root/.ollama ollama/ollama
docker exec seekspider-ollama ollama pull qwen3:14b
docker run --rm --entrypoint python -v "$PWD:/src:ro" -v /chemin/vers/resultats:/results \
  seekspider-run /src/targeted_search.py /results/offres.jsonl
docker run --rm --network container:seekspider-ollama --entrypoint python \
  -v "$PWD:/src:ro" -v /chemin/vers/resultats:/results \
  seekspider-run /src/local_rank.py /results/offres.jsonl /results/analyse.md --limit 20
```

La recherche parcourt les 42 intitulés Cloud, infrastructure, support et IA sur toute l'Australie, à raison d'une première page par intitulé. Les résultats SEEK peuvent contenir des postes voisins ; aucun filtre d'expérience, de visa ou de contrat n'est garanti par la recherche. Le classement dédoublonne les annonces et examine les descriptions de l'échantillon.

Pour utiliser un CV texte UTF-8 local, placer le fichier dans le dossier monté et ajouter `--profile /results/cv.txt`. Sans CV, le profil provisoire décrit dans le script est utilisé. Le dossier de résultats peut contenir des données personnelles : ne pas le publier. La récupération des offres passe par SEEK ; le CV et l'analyse sont envoyés uniquement au serveur Ollama sur `127.0.0.1` dans le réseau du conteneur. Le serveur est publié sur l'interface locale uniquement.

Pour redémarrer Ollama après un arrêt : `docker start seekspider-ollama`. Pour l'arrêter : `docker stop seekspider-ollama`.

