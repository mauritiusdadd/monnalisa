"""
Maurizio D'Addona <mauritiusdadd@gmail.com> (c) 2019 - 2020

monnalisa is a program to control da vinci printers
Copyright (C) 2013-2015  Maurizio D'Addona <mauritiusdadd@gmail.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
import setuptools

with open("README.md", "r") as fh:
    LONG_DESCRIPTION = fh.read()

setuptools.setup(
    name="monnalisa",
    version="0.1.4",
    author="Maurizio D'Addona",
    author_email="mauritiusdadd@gmail.com",
    description="An interface to control Da Vinci printers",
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
    url="<private>",
    packages=setuptools.find_packages(),
    classifiers=[
        'Development Status :: 3 - Alpha',
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    install_requires=[
        'PyQt5',
        'pyserial',
        'pycryptodome'
    ],
    extras_require={
        'Webcam interface for server': 'cv2',
    }, 
    entry_points={
        'console_scripts': [
            'monnalisa-server=monnalisa.server:main'
        ],
        'gui_scripts': [
            'monnalisa=monnalisa.xyzgui:main'
        ],
    },
    zip_safe=False,
    include_package_data=True
)
