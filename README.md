# openstack-fastrunner


## Install Guide
1. Install fastrunner
```
$ pip install .
```

2. Configuring fastrunner
You will find sample configuration files in `etc/`
```
$ cp -r etc /etc/fastrunner
```

3. Run fastrunner API
```
$ fastrunner-api
```

4. Run the following command to test api
```
curl -X GET 127.0.0.1:8774/v2.1/servers/detail -H "Accept: application/json" -H "X-Auth-Token: 123456"
```
