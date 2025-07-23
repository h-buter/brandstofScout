dockerPath=docker-compose.yml
sudo docker compose -f $dockerPath down -v 
sudo docker compose -f $dockerPath rm  -v 
sudo docker compose -f $dockerPath down --rmi all 
sudo docker compose -f $dockerPath build --no-cache 
sudo docker compose -f $dockerPath build
sudo docker compose -f $dockerPath up -d 
# sudo docker compose -f $dockerPath logs -f brandstof-scout
