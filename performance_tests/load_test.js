import http from 'k6/http';
import { check, sleep } from 'k6';

export let options = {
  vus: 10, // 10 virtual users
  duration: '30s', // run for 30 seconds
};

export default function () {
  const url = 'http://pan_service:5002/v1/pan/link-requests';
  const payload = JSON.stringify({
    panNumber: 'ABCDE1234F',
    customerName: 'Test User'
  });

  const params = {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      
      'Authorization': 'Bearer <YOUR_JWT_TOKEN>' 
    },
  };

  let res = http.post(url, payload, params);
  
  check(res, {
    'status is 201': (r) => r.status === 201,
  });

  sleep(1);
}