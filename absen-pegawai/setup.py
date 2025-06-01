from setuptools import setup, find_packages

setup(
    name="absensi-pegawai",
    version="1.0.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'flask==2.0.1',
        'flask-session==0.4.0',
        'python-dotenv==1.0.0',
        'psycopg2-binary==2.9.1',
        'werkzeug==2.0.1',
        'requests==2.31.0',
        'geopy==2.3.0',
        'mangum==0.17.0',
        'SQLAlchemy==1.4.23',
        'Flask-SQLAlchemy==2.5.1'
    ],
) 