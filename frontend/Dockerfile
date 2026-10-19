FROM node:20.19.5
WORKDIR /frontend

COPY package*.json ./

RUN npm ci
COPY . .

RUN npm run build
CMD ["npm", "start"]