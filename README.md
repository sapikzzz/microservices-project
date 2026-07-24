# Project Overview

This project is a distributed information system composed of independent services communicating through REST APIs and asynchronous messages.

The system includes at least three user roles, integration with two external services, OpenAPI documentation, JSON Schema or XML Schema validation, and a message broker such as RabbitMQ.

The architecture is documented using C4 Context and Container diagrams, while selected business processes are modeled in BPMN. The project also implements two integration processes: one based on choreography and one based on orchestration.

## System Context (C4)
<img width="2150" height="1704" alt="SystemContext" src="https://github.com/user-attachments/assets/c8ee1bf4-0493-4116-9f09-dc045290b93a" />

## Containers (C4)
<img width="6225" height="4054" alt="Containers" src="https://github.com/user-attachments/assets/28f0768a-a68b-46e4-9eda-f4e8d564e80e" />

## Main business process (BPMN)
<img width="3700" height="4188" alt="diagram" src="https://github.com/user-attachments/assets/091d8295-adcb-4698-af79-2450b7bdd753" />

## Sequence Diagrams

### Order sequence
<img width="1085" height="909" alt="Mikro - zamówienie" src="https://github.com/user-attachments/assets/dd23bc96-34bf-4b5f-ac3d-909bdefb9fc5" />

### User registration
<img width="913" height="472" alt="Mikro - Rejestracja Driver" src="https://github.com/user-attachments/assets/f3843158-358c-4662-9c9f-5a9ea852988d" />

### Delivery (client perspective)
<img width="1043" height="1070" alt="Mikro - Dostawa Klient" src="https://github.com/user-attachments/assets/30e23d2c-bbc4-41eb-b92c-87e2e1434ac3" />
