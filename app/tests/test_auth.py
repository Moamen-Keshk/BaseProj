import unittest
import json
import time

from app import db
from app.api.models import User
from app.tests.test_basics import BasicsTestCase


def register_user(self, email, password):
    return self.client.post(
        '/auth/register',
        data=json.dumps(dict(
            email=email,
            password=password
        )),
        content_type='application/json',
    )


class TestAuthBlueprint(BasicsTestCase):
    pass


if __name__ == '__main__':
    unittest.main()


def test_registration(self):
    """ Test for user registration """
    with self.client:
        response = self.client.post(
            '/auth/register',
            data=json.dumps(dict(
                email='joe@gmail.com',
                password='123456'
            )),
            content_type='application/json'
        )
        data = json.loads(response.data.decode())
        self.assertTrue(data['status'] == 'success')
        self.assertTrue(data['message'] == 'Successfully registered.')
        self.assertTrue(data['auth_token'])
        self.assertTrue(response.content_type == 'application/json')
        self.assertEqual(response.status_code, 201)


def test_registered_with_already_registered_user(self):
    """ Test registration with already registered email"""
    user = User(
        email='joe@gmail.com',
        password='test'
    )
    db.session.add(user)
    db.session.commit()
    with self.client:
        response = self.client.post(
            '/auth/register',
            data=json.dumps(dict(
                email='joe@gmail.com',
                password='123456'
            )),
            content_type='application/json'
        )
        data = json.loads(response.data.decode())
        self.assertTrue(data['status'] == 'fail')
        self.assertTrue(
            data['message'] == 'User already exists. Please Log in.')
        self.assertTrue(response.content_type == 'application/json')
        self.assertEqual(response.status_code, 202)


def test_registered_user_login(self):
    """ Test for login of registered-user login """
    with self.client:
        # user registration
        resp_register = self.client.post(
            '/auth/register',
            data=json.dumps(dict(
                email='joe@gmail.com',
                password='123456'
            )),
            content_type='application/json',
        )
        data_register = json.loads(resp_register.data.decode())
        self.assertTrue(data_register['status'] == 'success')
        self.assertTrue(
            data_register['message'] == 'Successfully registered.'
        )
        self.assertTrue(data_register['auth_token'])
        self.assertTrue(resp_register.content_type == 'application/json')
        self.assertEqual(resp_register.status_code, 201)
        # registered user login
        response = self.client.post(
            '/auth/login',
            data=json.dumps(dict(
                email='joe@gmail.com',
                password='123456'
            )),
            content_type='application/json'
        )
        data = json.loads(response.data.decode())
        self.assertTrue(data['status'] == 'success')
        self.assertTrue(data['message'] == 'Successfully logged in.')
        self.assertTrue(data['auth_token'])
        self.assertTrue(response.content_type == 'application/json')
        self.assertEqual(response.status_code, 200)


def test_non_registered_user_login(self):
    """ Test for login of non-registered user """
    with self.client:
        response = self.client.post(
            '/auth/login',
            data=json.dumps(dict(
                email='joe@gmail.com',
                password='123456'
            )),
            content_type='application/json'
        )
        data = json.loads(response.data.decode())
        self.assertTrue(data['status'] == 'fail')
        self.assertTrue(data['message'] == 'User does not exist.')
        self.assertTrue(response.content_type == 'application/json')
        self.assertEqual(response.status_code, 404)


def test_user_status(self):
    """ Test for user status """
    with self.client:
        resp_register = self.client.post(
            '/auth/register',
            data=json.dumps(dict(
                email='joe@gmail.com',
                password='123456'
            )),
            content_type='application/json'
        )
        response = self.client.get(
            '/auth/status',
            headers=dict(
                Authorization='Bearer ' + json.loads(
                    resp_register.data.decode()
                )['auth_token']
            )
        )
        data = json.loads(response.data.decode())
        self.assertTrue(data['status'] == 'success')
        self.assertTrue(data['data'] is not None)
        self.assertTrue(data['data']['email'] == 'joe@gmail.com')
        self.assertTrue(data['data']['admin'] is 'true' or 'false')
        self.assertEqual(response.status_code, 200)


def test_valid_logout(self):
    """ Test for logout before token expires """
    with self.client:
        # user registration
        resp_register = self.client.post(
            '/auth/register',
            data=json.dumps(dict(
                email='joe@gmail.com',
                password='123456'
            )),
            content_type='application/json',
        )
        data_register = json.loads(resp_register.data.decode())
        self.assertTrue(data_register['status'] == 'success')
        self.assertTrue(
            data_register['message'] == 'Successfully registered.')
        self.assertTrue(data_register['auth_token'])
        self.assertTrue(resp_register.content_type == 'application/json')
        self.assertEqual(resp_register.status_code, 201)
        # user login
        resp_login = self.client.post(
            '/auth/login',
            data=json.dumps(dict(
                email='joe@gmail.com',
                password='123456'
            )),
            content_type='application/json'
        )
        data_login = json.loads(resp_login.data.decode())
        self.assertTrue(data_login['status'] == 'success')
        self.assertTrue(data_login['message'] == 'Successfully logged in.')
        self.assertTrue(data_login['auth_token'])
        self.assertTrue(resp_login.content_type == 'application/json')
        self.assertEqual(resp_login.status_code, 200)
        # valid token logout
        response = self.client.post(
            '/auth/logout',
            headers=dict(
                Authorization='Bearer ' + json.loads(
                    resp_login.data.decode()
                )['auth_token']
            )
        )
        data = json.loads(response.data.decode())
        self.assertTrue(data['status'] == 'success')
        self.assertTrue(data['message'] == 'Successfully logged out.')
        self.assertEqual(response.status_code, 200)


def test_invalid_logout(self):
    """ Testing logout after the token expires """
    with self.client:
        # user registration
        resp_register = self.client.post(
            '/auth/register',
            data=json.dumps(dict(
                email='joe@gmail.com',
                password='123456'
            )),
            content_type='application/json',
        )
        data_register = json.loads(resp_register.data.decode())
        self.assertTrue(data_register['status'] == 'success')
        self.assertTrue(
            data_register['message'] == 'Successfully registered.')
        self.assertTrue(data_register['auth_token'])
        self.assertTrue(resp_register.content_type == 'application/json')
        self.assertEqual(resp_register.status_code, 201)
        # user login
        resp_login = self.client.post(
            '/auth/login',
            data=json.dumps(dict(
                email='joe@gmail.com',
                password='123456'
            )),
            content_type='application/json'
        )
        data_login = json.loads(resp_login.data.decode())
        self.assertTrue(data_login['status'] == 'success')
        self.assertTrue(data_login['message'] == 'Successfully logged in.')
        self.assertTrue(data_login['auth_token'])
        self.assertTrue(resp_login.content_type == 'application/json')
        self.assertEqual(resp_login.status_code, 200)
        # invalid token logout
        time.sleep(6)
        response = self.client.post(
            '/auth/logout',
            headers=dict(
                Authorization='Bearer ' + json.loads(
                    resp_login.data.decode()
                )['auth_token']
            )
        )
        data = json.loads(response.data.decode())
        self.assertTrue(data['status'] == 'fail')
        self.assertTrue(
            data['message'] == 'Signature expired. Please log in again.')
        self.assertEqual(response.status_code, 401)


def test_user_status_malformed_bearer_token(self):
    """ Test for user status with malformed bearer token"""
    with self.client:
        resp_register = register_user(self, 'joe@gmail.com', '123456')
        response = self.client.get(
            '/auth/status',
            headers=dict(
                Authorization='Bearer' + json.loads(
                    resp_register.data.decode()
                )['auth_token']
            )
        )
        data = json.loads(response.data.decode())
        self.assertTrue(data['status'] == 'fail')
        self.assertTrue(data['message'] == 'Bearer token malformed.')
        self.assertEqual(response.status_code, 401)
