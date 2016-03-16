#!/usr/bin/php
<?php
define('FACEBOOK_SDK_V4_SRC_DIR', '/share/lib/facebook-php-sdk-v4/src/Facebook/');
require '/share/lib/facebook-php-sdk-v4/autoload.php';

use Facebook\FacebookSession;
use Facebook\FacebookRequest;
use Facebook\GraphObject;
use Facebook\FacebookRequestException;

$icon = "http://mystic.ses.nsw.gov.au/icons/beacon.png";

// Parse arguments

switch ($argc) {
    case 3:
        $type = $argv[1];
        $message = $argv[2];
        break;
    default:
        printf("Usage: %s Type Message\n", $argv[0]);
}

switch ($type) {
    case "132500":
        $name = "132500 Message";
        break;
    case "SUPPORT":
        $name = "Support Message";
        break;
    case "VR":
    case "GLR":
    case "FR":
        $name = "Rescue Message";
        break;
    default:
        $name = "Other Message";
        break;
}

FacebookSession::setDefaultApplication('<fb-app-id>', '<fb-app-secret>');
$session = new FacebookSession('<fb-app-token>');

if($session) {

  try {
    $response = (new FacebookRequest(
      $session, 'POST', '/<fb-group-id>/feed', array(
        'picture' => $icon,
        'message' => $message,
        'name' => $name,
        'link' => 'http://beacon.ses.nsw.gov.au'
      )
    ))->execute()->getGraphObject();
  } catch(FacebookRequestException $e) {
    echo "Exception occured, code: " . $e->getCode();
    echo " with message: " . $e->getMessage() . "\n";
  }

}

?>
