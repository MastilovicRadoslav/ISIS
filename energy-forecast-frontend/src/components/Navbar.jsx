import React from "react";
import { Link } from "react-router-dom";
import { Menu } from "antd";

const items = [
  {
    key: "upload",
    label: <Link to="/upload">Upload</Link>,
  },
];

const Navbar = () => {
  return (
    <Menu mode="horizontal" theme="dark" style={{ paddingLeft: 24 }} items={items} />
  );
};

export default Navbar;
